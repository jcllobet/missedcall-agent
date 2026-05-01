# Architecture

## Call Control

Twilio owns the phone call. Pipecat only starts when the caller needs the AI
fallback.

```text
Caller dials Twilio number
  |
  v
Twilio Function /voice
  |
  v
Caller is parked in a Twilio queue
  |
  +--> Twilio starts a separate call to Jan
         |
         v
       Jan hears: "Press 1 to accept"
         |
         +-- presses 1 --------------------+
         |                                  |
         v                                  v
       Twilio dequeues caller           Caller talks to Jan
       into Jan call                    AI is not involved

         |
         +-- no answer / decline / no key / voicemail
                                            |
                                            v
                                  Twilio leaves queue
                                            |
                                            v
                                  Function asks Pipecat Cloud
                                  for one short-lived token URL
                                            |
                                            v
                                  Twilio streams caller audio
                                  to Pipecat Cloud
```

## AI Audio Chain

Once Twilio starts the fallback stream, audio moves through the bot like this:

```text
PSTN caller audio
  |
  v
Twilio Media Stream
  |
  |  websocket audio frames
  v
Pipecat Cloud bot.py
  |
  |  caller speech audio
  v
Deepgram STT
  |
  |  transcript text
  v
OpenAI LLM
  |
  |  assistant reply text
  v
Cartesia TTS
  |
  |  assistant speech audio
  v
Pipecat Cloud
  |
  |  websocket audio frames
  v
Twilio Media Stream
  |
  v
Caller hears AI voicemail
```

## End Of Call

```text
Caller hangs up
  |
  v
Pipecat finalizes transcript
  |
  v
OpenAI summarizes voicemail
  |
  v
Slack recap is posted to Jan
```

## Security Boundary

```text
Public repo:
  - placeholder agent name
  - placeholder secret set
  - no API keys
  - websocket_auth = "token"

Private runtime:
  - real Pipecat service host
  - PCC_PUBLIC_KEY
  - Twilio credentials
  - OpenAI / Deepgram / Cartesia / Slack secrets
```
