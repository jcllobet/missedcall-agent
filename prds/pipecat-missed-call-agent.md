---
title: Pipecat Missed-Call Agent
description: Replace the LiveKit SIP flow with a Twilio and Pipecat voicemail agent that rings Jan first and handles missed calls.
---

# Pipecat Missed-Call Agent

## Summary

Build Jan's AI voicemail as a Twilio-first call workflow with Pipecat Cloud
handling the AI fallback leg. A caller calls Jan's Twilio number, Twilio rings
Jan's fixed phone number, and if Jan does not answer within the configured
timeout, Twilio connects the still-active caller to a Pipecat Cloud voice bot
over Media Streams. After the AI conversation, the bot sends Jan a Slack recap.

## Customer / User

Jan is the primary user. Callers are people trying to reach Jan who should not
hit a dead voicemail box when Jan misses the call.

## Problem

The LiveKit SIP setup added too much operational friction for the MVP: inbound
trunks, outbound trunks, dispatch rules, cloud agent identity, and Twilio SIP
credentials created too many places where the demo could fail. Twilio already
knows how to ring Jan and report whether Jan answered. Pipecat should focus on
the useful AI voicemail conversation after Twilio determines the human did not
pick up.

## Why Now

The next useful milestone is an end-to-end phone call, not a perfect agent
platform abstraction. Twilio webhooks plus Pipecat Cloud Media Streams are
easier to observe with FastAPI/ngrok for call control, Twilio logs, Pipecat
Cloud logs, and Slack output.

## MVP Goal

One Twilio number can:

1. Ring Jan's fixed phone number.
2. Detect no-answer, busy, or failed dial status.
3. Connect the original caller to a Pipecat Cloud AI voicemail.
4. Capture transcript, fallback recording, summary, and action items.
5. Send Jan a Slack recap.

## Success Signal

A real phone call proves both branches:

- Jan answers: caller speaks to Jan, AI never speaks, no AI recap is sent.
- Jan misses: caller hears the Pipecat AI voicemail, completes a useful
  conversation, and Jan receives a Slack recap.

## Non-goals

- LiveKit compatibility.
- Multi-agent routing.
- Dashboard, authentication, CRM, calendar, or database.
- AI speaking during a successful human call.
- A generic call center product.

## Evidence Reviewed

- Pipecat Cloud's Twilio guide says Twilio should stream to
  `wss://api.pipecat.daily.co/ws/twilio` with `_pipecatCloudServiceHost`.
- Pipecat's Twilio guide documents dial-out through Twilio REST and TwiML, but
  this MVP does not need Pipecat to initiate a separate bot-to-human call.
- Pipecat Cloud agent images require a root `bot.py` with an async `bot()`
  entrypoint.
- Twilio `<Dial>` supports `timeout` and `action`, and sends `DialCallStatus`
  such as `completed`, `busy`, `no-answer`, or `failed`.
- The existing repo already has the useful Jan prompt, call record model, and
  Slack recap renderer.

## Architecture

```text
Caller
  |
  v
Twilio phone number
  |
  v
FastAPI POST /voice
  |
  v
TwiML <Dial Jan timeout action=/dial-status>
  | answered
  v
Jan speaks to caller; app does nothing else

TwiML <Dial Jan timeout action=/dial-status>
  | no-answer / busy / failed
  v
FastAPI POST /dial-status
  |
  v
TwiML <Connect><Stream url=wss://api.pipecat.daily.co/ws/twilio>
  |
  v
Pipecat Cloud bot.py
  |
  v
Deepgram STT -> OpenAI LLM -> ElevenLabs TTS
  |
  v
Slack recap
```

## Implementation Plan

- Move LiveKit files under `archive/livekit/` and remove LiveKit dependencies.
- Replace the active server with FastAPI Twilio call-control webhooks.
- Add a Pipecat Cloud `bot.py` entrypoint and `pcc-deploy.toml`.
- Make the fallback TwiML stream to Pipecat Cloud with
  `_pipecatCloudServiceHost`.
- Add Pipecat, Twilio, Deepgram, and ElevenLabs dependencies.
- Update `.env.example` to only include the Pipecat/Twilio variables.
- Keep the Jan voicemail prompt, record store, and Slack recap.
- Update README with Twilio webhook setup and local ngrok test flow.

## Verification

- `uv run python -m compileall src tests`
- `uv run pytest -q`
- `GET /health` shows missing runtime variables until `.env` is filled.
- `GET /twiml-preview` returns a `<Dial>` that points at `/dial-status`.
- With ngrok, Pipecat Cloud, and real secrets, a missed call reaches Pipecat
  Cloud and produces a Slack recap.

## Acceptance Criteria

- No active runtime imports LiveKit.
- Twilio number setup uses a webhook to `/voice`, not a TwiML Bin.
- Missed calls route to Pipecat Cloud over Twilio Media Streams.
- Answered human calls do not invoke Pipecat.
- Slack recap still includes caller, fallback reason, summary, and action items.

## Risks / Open Questions

- The MVP needs new service keys: `DEEPGRAM_API_KEY` and `ELEVENLABS_API_KEY`.
- Twilio adds a small buffer to `<Dial timeout>`, so a ten second setting may
  ring for slightly longer in practice.
- A mobile carrier voicemail answering Jan's phone can look like a completed
  human answer to Twilio. For the MVP, this is accepted; answering-machine
  detection can be added later if it becomes a real failure.
