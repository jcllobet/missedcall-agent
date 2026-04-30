# missedcall-agent

Jan AI Voicemail: inbound callers ring Jan first through Twilio. If Jan does
not answer, Twilio streams the still-active caller to a Pipecat Cloud voice bot
and the bot sends Jan a Slack recap.

## Architecture

```text
Caller
  |
  v
Twilio number
  |
  v
FastAPI /voice
  |
  v
<Dial Jan timeout=10 action=/dial-status>
  | answered                       | no-answer / busy / failed
  v                                v
Human call                         FastAPI /dial-status
ends                               |
                                   v
                         <Connect><Stream Pipecat Cloud>
                                   |
                                   v
                         Pipecat Cloud bot.py
                                   |
                                   v
                         Slack recap + call record
```

## Runtime Pieces

- `src/missed_call_agent/main.py`: small FastAPI call-control service for Twilio webhooks.
- `bot.py`: Pipecat Cloud agent entrypoint.
- `Dockerfile`: Pipecat Cloud agent image.
- `Dockerfile.web`: optional FastAPI call-control image if hosting it in a container.

## Setup

```bash
cp .env.example .env
uv sync --extra dev
```

Required `.env` values:

```text
PUBLIC_BASE_URL=
PIPECAT_CLOUD_SERVICE_HOST=jan-ai-voicemail.jan-agent-swarm
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
JAN_PHONE_NUMBER=
OPENAI_API_KEY=
DEEPGRAM_API_KEY=
ELEVENLABS_API_KEY=
SLACK_BOT_TOKEN=
SLACK_CHANNEL_ID=
```

`PUBLIC_BASE_URL` is the HTTPS URL where Twilio can reach the FastAPI call-control app.
For local testing, use ngrok:

```bash
uv run uvicorn missed_call_agent.main:app --reload --port 8000
ngrok http 8000
```

`PIPECAT_CLOUD_SERVICE_HOST` is:

```text
jan-ai-voicemail.jan-agent-swarm
```

Use the regional Pipecat Cloud WebSocket URL only if you deploy outside the
default region:

```text
PIPECAT_CLOUD_WS_URL=wss://api.pipecat.daily.co/ws/twilio
```

## Deploy Pipecat Cloud Agent

Pipecat Cloud provisions the Daily infrastructure. You do not need a separate
Daily API key for this Twilio Media Streams path.

Authenticate:

```bash
pipecat cloud auth login
```

Upload secrets:

```bash
pipecat cloud secrets set jan-ai-voicemail-secrets --file .env
```

Deploy:

```bash
pipecat cloud deploy
```

The deployment uses `pcc-deploy.toml`, `Dockerfile`, and `bot.py`.
If the CLI is not installed globally, prefix commands with:

```bash
uvx --from pipecat-ai-cli pipecat
```

## Twilio Number Setup

In the Twilio phone number Voice Configuration:

```text
A call comes in: Webhook
URL: https://<PUBLIC_BASE_URL>/voice
HTTP: POST

Primary handler fails: blank
Call status changes: blank
Caller Name Lookup: Disabled
```

Do not point the Twilio number directly at Pipecat Cloud, because this product
needs Twilio to ring Jan first and only stream to AI after a missed call.

## Test

1. Deploy the Pipecat Cloud agent.
2. Start or deploy the FastAPI call-control service.
3. Set `PUBLIC_BASE_URL` to the call-control service URL.
4. Configure the Twilio number webhook to `https://<PUBLIC_BASE_URL>/voice`.
5. Call the Twilio number.
6. Let Jan's phone ring without answering.
7. Confirm the caller hears the AI voicemail.
8. Hang up and confirm Slack receives a recap.

If Jan answers, the caller should connect to Jan and the AI should not speak.

## Useful FastAPI Endpoints

- `GET /health`: missing configuration check.
- `POST /voice`: Twilio inbound call webhook.
- `POST /dial-status`: Twilio `<Dial>` result webhook.
- `GET /twiml-preview`: preview the initial ring-Jan TwiML.

## Legacy LiveKit Files

The old LiveKit deployment files are archived under `archive/livekit/` only for
reference. The active agent runtime is Pipecat Cloud.
