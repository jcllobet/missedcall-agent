"""End-to-end voice test: synthetic human ↔ bot, two turns.

Exercises every external service used in production (Cartesia TTS for both
speakers, Deepgram STT for the human side, OpenAI for the bot's replies)
without involving Twilio or Pipecat's audio pipeline. The Pipecat
orchestration is verified by manual phone calls; this test covers the
vendor integrations and the prompt logic across two conversational turns.

LLM uses temperature=0 so successive runs return broadly the same shape
of reply. The assertions are intentionally loose (non-empty audio,
non-empty transcripts, message-count alternation) so wording variation
in OpenAI replies cannot flake the test.
"""

from __future__ import annotations

import os

import httpx
import pytest
from openai import AsyncOpenAI

from missed_call_agent.config import get_settings
from missed_call_agent.prompts import VOICEMAIL_GREETING, voicemail_instructions

CARTESIA_BASE = "https://api.cartesia.ai"
CARTESIA_VERSION = "2026-03-01"
DEEPGRAM_BASE = "https://api.deepgram.com"
BOT_VOICE_ID = "62ae83ad-4f6a-430b-af41-a9bede9286ca"
HUMAN_VOICE_ID = "5ee9feff-1265-424a-9d7f-8e4d431a12c7"
CARTESIA_MODEL = "sonic-3"

HUMAN_TURNS = [
    "Hi, this is Alice from Acme. I'd like to leave a message about a meeting tomorrow at 3 pm.",
    "Yes, please tell Jan to confirm by email.",
]

MIN_AUDIO_BYTES = 2000  # WAV header + a few samples; anything smaller is suspect
LLM_MODEL = "gpt-4.1-mini"


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} not set; skipping e2e voice test")
    return value


async def cartesia_tts(text: str, voice_id: str, api_key: str) -> bytes:
    payload = {
        "model_id": CARTESIA_MODEL,
        "transcript": text,
        "voice": {"mode": "id", "id": voice_id},
        "output_format": {
            "container": "wav",
            "encoding": "pcm_s16le",
            "sample_rate": 16000,
        },
        "language": "en",
        "generation_config": {"speed": 1, "volume": 1},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{CARTESIA_BASE}/tts/bytes",
            headers={
                "Cartesia-Version": CARTESIA_VERSION,
                "X-API-Key": api_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        return response.content


async def deepgram_transcribe(audio_wav: bytes, api_key: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{DEEPGRAM_BASE}/v1/listen?model=nova-3&smart_format=true&punctuate=true",
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "audio/wav",
            },
            content=audio_wav,
        )
        response.raise_for_status()
        data = response.json()
    channels = data.get("results", {}).get("channels") or []
    if not channels:
        return ""
    alternatives = channels[0].get("alternatives") or []
    if not alternatives:
        return ""
    return (alternatives[0].get("transcript") or "").strip()


async def llm_reply(messages: list[dict], openai_api_key: str) -> str:
    client = AsyncOpenAI(api_key=openai_api_key)
    response = await client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=0,
    )
    return (response.choices[0].message.content or "").strip()


async def test_two_turn_voice_conversation() -> None:
    cartesia_key = _required_env("CARTESIA_API_KEY")
    deepgram_key = _required_env("DEEPGRAM_API_KEY")
    openai_key = _required_env("OPENAI_API_KEY")

    settings = get_settings()
    messages: list[dict] = [
        {"role": "system", "content": voicemail_instructions(settings)},
        {
            "role": "user",
            "content": (
                "Start the call by greeting the caller with this exact message: "
                f"{VOICEMAIL_GREETING}"
            ),
        },
    ]

    bot_audio_chunks: list[bytes] = []
    transcripts: list[str] = []

    # Bot turn 0 — greeting
    greeting = await llm_reply(messages, openai_key)
    assert greeting, "bot greeting was empty"
    audio = await cartesia_tts(greeting, BOT_VOICE_ID, cartesia_key)
    assert len(audio) > MIN_AUDIO_BYTES, f"bot greeting audio too small: {len(audio)} bytes"
    bot_audio_chunks.append(audio)
    messages.append({"role": "assistant", "content": greeting})

    # Human + bot turns
    for human_text in HUMAN_TURNS:
        # Synthetic human speaks (different Cartesia voice — distinguishable)
        human_audio = await cartesia_tts(human_text, HUMAN_VOICE_ID, cartesia_key)
        assert len(human_audio) > MIN_AUDIO_BYTES, "human audio too small"

        # STT
        transcript = await deepgram_transcribe(human_audio, deepgram_key)
        assert transcript, f"deepgram returned empty transcript for: {human_text!r}"
        transcripts.append(transcript)
        messages.append({"role": "user", "content": transcript})

        # Bot replies
        bot_text = await llm_reply(messages, openai_key)
        assert bot_text, "bot reply was empty"

        # Bot's TTS
        bot_audio = await cartesia_tts(bot_text, BOT_VOICE_ID, cartesia_key)
        assert len(bot_audio) > MIN_AUDIO_BYTES, "bot reply audio too small"
        bot_audio_chunks.append(bot_audio)
        messages.append({"role": "assistant", "content": bot_text})

    # Assertions: full back-and-forth happened
    user_msgs = [
        m for m in messages
        if m["role"] == "user" and not m["content"].startswith("Start the call")
    ]
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    assert len(user_msgs) == 2, f"expected 2 user turns, got {len(user_msgs)}"
    assert len(assistant_msgs) == 3, (
        f"expected 3 assistant turns (greeting + 2 replies), got {len(assistant_msgs)}"
    )
    assert len(bot_audio_chunks) == 3, f"expected 3 bot audio chunks, got {len(bot_audio_chunks)}"
    assert all(len(chunk) > MIN_AUDIO_BYTES for chunk in bot_audio_chunks)
    assert all(transcript for transcript in transcripts)

    # Sanity check: STT roughly captured the human script. Keep this loose
    # because short names can transcribe as common homophones.
    token_variants = {"alice": ("alice",), "jan": ("jan", "jen")}
    for original, recovered in zip(HUMAN_TURNS, transcripts):
        # Pick a couple of distinctive lowercase tokens from the original.
        for token, variants in token_variants.items():
            if token in original.lower():
                recovered_lower = recovered.lower()
                assert any(variant in recovered_lower for variant in variants), (
                    f"deepgram did not recover {token!r} from {original!r}; got {recovered!r}"
                )
