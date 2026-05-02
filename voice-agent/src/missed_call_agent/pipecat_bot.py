import datetime
import io
import traceback
import wave
from pathlib import Path
from typing import Any

import aiofiles
from loguru import logger
from openai import AsyncOpenAI
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    EndTaskFrame,
    FunctionCallResultProperties,
    LLMRunFrame,
    TTSSpeakFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.runner.types import WebSocketRunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService, LiveOptions
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport

from .config import Settings, get_settings
from .prompts import VOICEMAIL_ENDING, VoiceProfile, voicemail_greeting, voicemail_instructions
from .records import CallRecord, CallRecordStore, summarize_transcript_placeholder, utc_now
from .slack import post_slack_recap
from .slack_log import log_call_success, log_failure

END_CALL_FUNCTION = FunctionSchema(
    name="end_call",
    description=(
        "Say the final goodbye sentence and end the phone call when the voicemail "
        "conversation is complete."
    ),
    properties={},
    required=[],
)


def _slack_failure(settings: Settings, service: str, exc: BaseException, record: CallRecord) -> None:
    log_failure(
        settings.slack_bot_token,
        settings.slack_log_channel_id,
        service=service,
        error_summary=f"{type(exc).__name__}: {exc}",
        detail=traceback.format_exc(),
        caller_number=record.caller_number,
        call_sid=record.room_name,
    )


def _body_value(body: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = body.get(key)
        if value:
            return str(value)
    return None


def transcript_from_context(context: LLMContext) -> list[dict[str, str]]:
    transcript: list[dict[str, str]] = []
    for message in context.get_messages():
        role = str(message.get("role", ""))
        if role not in {"user", "assistant"}:
            continue
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if content.startswith("Start the call by greeting the caller"):
            continue
        transcript.append({"speaker": "caller" if role == "user" else "assistant", "text": content})
    return transcript


async def summarize_with_openai(settings: Settings, transcript: list[dict[str, str]]) -> tuple[str, list[str]]:
    if not transcript or not settings.openai_api_key:
        return summarize_transcript_placeholder(transcript)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    conversation = "\n".join(f"{item['speaker']}: {item['text']}" for item in transcript)
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Summarize this missed-call voicemail for Jan. Return concise plain text with "
                    "a Summary line and Action items as short bullets."
                ),
            },
            {"role": "user", "content": conversation},
        ],
        temperature=0.2,
    )
    text = response.choices[0].message.content or ""
    action_items = [
        line.strip("- ").strip()
        for line in text.splitlines()
        if line.strip().startswith("-") and line.strip("- ").strip()
    ]
    summary_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("-") and "action item" not in line.lower()
    ]
    summary = " ".join(summary_lines).replace("Summary:", "").strip() or text[:500]
    return summary, action_items or ["Review transcript and follow up if needed."]


async def fetch_voice_profile(settings: Settings, profile_id: str | None) -> VoiceProfile | None:
    if not profile_id or not settings.product_api_base_url or not settings.product_api_key:
        return None

    url = f"{settings.product_api_base_url.rstrip('/')}/api/runtime/profiles/{profile_id}"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            url,
            headers={"Authorization": f"Bearer {settings.product_api_key}"},
        )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    data = response.json()
    return VoiceProfile(
        assistant_name=str(data.get("assistantName") or "AI Assistant"),
        greeting=str(data.get("greeting") or ""),
        system_prompt=str(data.get("systemPrompt") or ""),
    )


async def save_audio(output_dir: Path, call_sid: str | None, audio: bytes, sample_rate: int, channels: int) -> str | None:
    if not audio:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_call_sid = call_sid or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"{safe_call_sid}.wav"
    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as wav:
            wav.setsampwidth(2)
            wav.setnchannels(channels)
            wav.setframerate(sample_rate)
            wav.writeframes(audio)
        async with aiofiles.open(path, "wb") as file:
            await file.write(buffer.getvalue())
    return str(path)


async def finalize_record(record: CallRecord) -> None:
    settings = get_settings()
    record.ended_at = utc_now()
    store = CallRecordStore(settings.call_output_dir)
    path = store.save(record)

    if settings.slack_bot_token and settings.slack_channel_id:
        try:
            record.slack_ts = await post_slack_recap(
                settings.slack_bot_token,
                settings.slack_channel_id,
                record,
                str(path),
            )
            store.save(record)
        except Exception:
            logger.exception("Failed to send Slack recap")
    else:
        logger.warning("Skipping Slack recap; missing SLACK_BOT_TOKEN or SLACK_CHANNEL_ID")


async def end_call(params: FunctionCallParams) -> None:
    params.context.add_message({"role": "assistant", "content": VOICEMAIL_ENDING})
    await params.llm.push_frame(TTSSpeakFrame(VOICEMAIL_ENDING, append_to_context=False))
    await params.result_callback(
        {"status": "ending_call"},
        properties=FunctionCallResultProperties(run_llm=False),
    )
    await params.llm.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)


async def run_voicemail_pipeline(
    transport: BaseTransport,
    record: CallRecord,
    handle_sigint: bool,
    profile: VoiceProfile | None = None,
) -> None:
    settings = get_settings()

    try:
        llm = OpenAILLMService(api_key=settings.openai_api_key, model=settings.openai_model)
    except Exception as exc:
        _slack_failure(settings, "openai", exc, record)
        raise
    try:
        stt = DeepgramSTTService(
            api_key=settings.deepgram_api_key or "",
            live_options=LiveOptions(
                model=settings.deepgram_model,
                language="en",
                punctuate=True,
                smart_format=True,
                interim_results=True,
            ),
        )
    except Exception as exc:
        _slack_failure(settings, "deepgram", exc, record)
        raise
    try:
        tts = CartesiaTTSService(
            api_key=settings.cartesia_api_key or "",
            voice_id=settings.cartesia_voice_id,
            model=settings.cartesia_model,
        )
    except Exception as exc:
        _slack_failure(settings, "cartesia", exc, record)
        raise

    llm.register_function("end_call", end_call)
    context = LLMContext(
        messages=[{"role": "system", "content": voicemail_instructions(settings, profile)}],
        tools=ToolsSchema(standard_tools=[END_CALL_FUNCTION]),
    )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )
    audio_buffer = AudioBufferProcessor()

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            audio_buffer,
            assistant_aggregator,
        ]
    )
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _client):
        await audio_buffer.start_recording()
        context.add_message(
            {
                "role": "user",
                "content": (
                    "Start the call by greeting the caller with this exact message: "
                    f"{voicemail_greeting(profile)}"
                ),
            }
        )
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _client):
        await task.cancel()

    @audio_buffer.event_handler("on_audio_data")
    async def on_audio_data(_buffer, audio, sample_rate, num_channels):
        record.recording_ref = await save_audio(
            settings.call_output_dir / "recordings",
            record.room_name,
            audio,
            sample_rate,
            num_channels,
        )

    runner = PipelineRunner(handle_sigint=handle_sigint, force_gc=True)
    pipeline_error: BaseException | None = None
    try:
        await runner.run(task)
    except BaseException as exc:
        pipeline_error = exc
        _slack_failure(settings, "pipecat", exc, record)
        raise
    finally:
        record.transcript = transcript_from_context(context)
        try:
            record.summary, record.action_items = await summarize_with_openai(settings, record.transcript)
        except Exception as exc:
            _slack_failure(settings, "openai", exc, record)
            record.summary, record.action_items = summarize_transcript_placeholder(record.transcript)
        try:
            await finalize_record(record)
        except Exception as exc:
            _slack_failure(settings, "slack", exc, record)
        if pipeline_error is None:
            log_call_success(
                settings.slack_bot_token,
                settings.slack_log_channel_id,
                record.caller_number,
                record.transcript,
                record.room_name,
            )


async def run_twilio_bot(runner_args: WebSocketRunnerArguments) -> None:
    settings = get_settings()
    placeholder_record = CallRecord(caller_number=None, room_name=None, fallback_reason="jan_no_answer")
    try:
        _, call_data = await parse_telephony_websocket(runner_args.websocket)
    except Exception as exc:
        _slack_failure(settings, "twilio", exc, placeholder_record)
        raise
    body = call_data.get("body") or {}
    call_sid = call_data.get("call_id")
    stream_sid = call_data.get("stream_id")

    record = CallRecord(
        caller_number=_body_value(body, "caller", "From", "from"),
        room_name=call_sid,
        fallback_reason=_body_value(body, "fallback_reason") or "jan_no_answer",
    )
    profile = await fetch_voice_profile(settings, _body_value(body, "profile_id", "profileId"))

    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=settings.twilio_account_sid,
        auth_token=settings.twilio_auth_token,
    )
    transport = FastAPIWebsocketTransport(
        websocket=runner_args.websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )
    await run_voicemail_pipeline(transport, record, runner_args.handle_sigint, profile)
