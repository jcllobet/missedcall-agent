"""Lightweight async logging to a dedicated Slack ops channel.

Calls into this module never block the audio pipeline: every Slack post is
scheduled via ``asyncio.create_task`` and any error in the post itself is
swallowed (logged locally) so a Slack outage cannot stall a call.
"""

import asyncio
from typing import Any

import httpx
from loguru import logger

SERVICE_LABELS: dict[str, str] = {
    "twilio": "Twilio",
    "pipecat": "Pipecat",
    "cartesia": "Cartesia TTS",
    "deepgram": "Deepgram STT",
    "openai": "OpenAI",
    "slack": "Slack",
}

_MAX_SUMMARY = 140
_MAX_DETAIL = 2800


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


async def _post(
    token: str,
    channel_id: str,
    text: str,
    blocks: list[dict[str, Any]] | None = None,
    thread_ts: str | None = None,
) -> str | None:
    if not token or not channel_id:
        return None
    payload: dict[str, Any] = {"channel": channel_id, "text": text}
    if blocks:
        payload["blocks"] = blocks
    if thread_ts:
        payload["thread_ts"] = thread_ts
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.error("slack_log post failed: {}", exc)
        return None
    if not data.get("ok"):
        logger.error("slack_log API error: {}", data.get("error"))
        return None
    return data.get("ts")


async def _log_call_success(
    token: str,
    channel_id: str,
    caller_number: str | None,
    transcript: list[dict[str, str]],
    call_sid: str | None,
) -> None:
    caller = caller_number or "unknown"
    turns = len(transcript)
    summary = f":white_check_mark: Call from `{caller}` handled — {turns} turns"
    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": summary}},
    ]
    if call_sid:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"Call SID `{call_sid}`"}],
            }
        )
    main_ts = await _post(token, channel_id, summary, blocks)
    if main_ts and transcript:
        lines = [
            f"*{item['speaker']}:* {item['text']}" for item in transcript if item.get("text")
        ]
        body = _truncate("\n".join(lines), _MAX_DETAIL)
        if body:
            await _post(
                token,
                channel_id,
                "Transcript",
                [{"type": "section", "text": {"type": "mrkdwn", "text": body}}],
                thread_ts=main_ts,
            )


async def _log_failure(
    token: str,
    channel_id: str,
    service: str,
    error_summary: str,
    detail: str | None,
    caller_number: str | None,
    call_sid: str | None,
) -> None:
    label = SERVICE_LABELS.get(service, service)
    one_line = _truncate(error_summary, _MAX_SUMMARY)
    headline = f":red_circle: *{label}* — {one_line}"
    context_bits = []
    if caller_number:
        context_bits.append(f"caller `{caller_number}`")
    if call_sid:
        context_bits.append(f"sid `{call_sid}`")
    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": headline}},
    ]
    if context_bits:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": " · ".join(context_bits)}],
            }
        )
    main_ts = await _post(token, channel_id, f":red_circle: {label}: {one_line}", blocks)
    if main_ts and detail:
        body = _truncate(detail, _MAX_DETAIL)
        await _post(
            token,
            channel_id,
            "Details",
            [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"```{body}```"},
                }
            ],
            thread_ts=main_ts,
        )


def log_call_success(
    token: str | None,
    channel_id: str | None,
    caller_number: str | None,
    transcript: list[dict[str, str]],
    call_sid: str | None,
) -> None:
    """Fire-and-forget success log. Never blocks; never raises."""
    if not token or not channel_id:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("slack_log: no running loop, dropping success event")
        return
    loop.create_task(
        _log_call_success(token, channel_id, caller_number, transcript, call_sid)
    )


def log_failure(
    token: str | None,
    channel_id: str | None,
    service: str,
    error_summary: str,
    detail: str | None = None,
    caller_number: str | None = None,
    call_sid: str | None = None,
) -> None:
    """Fire-and-forget failure log. Never blocks; never raises."""
    if not token or not channel_id:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("slack_log: no running loop, dropping failure event")
        return
    loop.create_task(
        _log_failure(
            token,
            channel_id,
            service,
            error_summary,
            detail,
            caller_number,
            call_sid,
        )
    )
