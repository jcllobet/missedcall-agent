import datetime
import io
import os
import wave
from pathlib import Path
from typing import Any

import aiofiles
from loguru import logger
from openai import AsyncOpenAI
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.runner.types import WebSocketRunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.deepgram.stt import DeepgramSTTService, LiveOptions
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat.turns.user_mute.mute_until_first_bot_complete_user_mute_strategy import (
    MuteUntilFirstBotCompleteUserMuteStrategy,
)
from pipecat.turns.user_start.min_words_user_turn_start_strategy import (
    MinWordsUserTurnStartStrategy,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies

from .config import Settings, get_settings
from .prompts import VOICEMAIL_GREETING, voicemail_instructions
from .records import CallRecord, CallRecordStore, summarize_transcript_placeholder, utc_now
from .slack import post_slack_recap


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


PIPELINE_SAMPLE_RATE = 24000
TWILIO_SAMPLE_RATE = 8000


async def run_voicemail_pipeline(
    transport: BaseTransport,
    record: CallRecord,
    handle_sigint: bool,
) -> None:
    settings = get_settings()
    llm = OpenAILLMService(api_key=settings.openai_api_key, model=settings.openai_model)
    stt = DeepgramSTTService(
        api_key=settings.deepgram_api_key or "",
        sample_rate=PIPELINE_SAMPLE_RATE,
        live_options=LiveOptions(
            model=settings.deepgram_model,
            language="en",
            punctuate=True,
            smart_format=True,
            interim_results=True,
        ),
    )
    tts = ElevenLabsTTSService(
        api_key=settings.elevenlabs_api_key or "",
        voice_id=settings.elevenlabs_voice_id,
        model=settings.elevenlabs_model,
        sample_rate=PIPELINE_SAMPLE_RATE,
        params=ElevenLabsTTSService.InputParams(
            stability=settings.elevenlabs_stability,
            similarity_boost=settings.elevenlabs_similarity_boost,
            style=settings.elevenlabs_style,
            speed=settings.elevenlabs_speed,
            use_speaker_boost=settings.elevenlabs_use_speaker_boost,
        ),
    )

    context = LLMContext(messages=[{"role": "system", "content": voicemail_instructions(settings)}])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(
                sample_rate=PIPELINE_SAMPLE_RATE,
                params=VADParams(confidence=settings.vad_confidence),
            ),
            user_turn_strategies=UserTurnStrategies(
                start=[MinWordsUserTurnStartStrategy(min_words=2)],
            ),
            user_mute_strategies=[MuteUntilFirstBotCompleteUserMuteStrategy()],
        ),
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
            audio_in_sample_rate=PIPELINE_SAMPLE_RATE,
            audio_out_sample_rate=PIPELINE_SAMPLE_RATE,
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
                "content": f"Start the call by greeting the caller with this exact message: {VOICEMAIL_GREETING}",
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
    try:
        await runner.run(task)
    finally:
        record.transcript = transcript_from_context(context)
        record.summary, record.action_items = await summarize_with_openai(settings, record.transcript)
        await finalize_record(record)


async def run_twilio_bot(runner_args: WebSocketRunnerArguments) -> None:
    settings = get_settings()
    _, call_data = await parse_telephony_websocket(runner_args.websocket)
    body = call_data.get("body") or {}
    call_sid = call_data.get("call_id")
    stream_sid = call_data.get("stream_id")

    record = CallRecord(
        caller_number=_body_value(body, "caller", "From", "from"),
        room_name=call_sid,
        fallback_reason=_body_value(body, "fallback_reason") or "jan_no_answer",
    )

    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=settings.twilio_account_sid,
        auth_token=settings.twilio_auth_token,
        params=TwilioFrameSerializer.InputParams(
            twilio_sample_rate=TWILIO_SAMPLE_RATE,
            sample_rate=PIPELINE_SAMPLE_RATE,
        ),
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
    await run_voicemail_pipeline(transport, record, runner_args.handle_sigint)
