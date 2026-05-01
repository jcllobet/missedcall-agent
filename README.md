# missedcall-agent

Jan AI Voicemail rings Jan first through Twilio. If Jan does not answer or does
not press `1`, Twilio sends the still-active caller to a Pipecat Cloud voice bot,
then the bot sends Jan a Slack recap.

See [docs/architecture.md](docs/architecture.md) for the call flow and audio/AI
chain.

## Setup

```bash
cp .env.example .env
uv sync --extra dev
```

Required runtime values:

```text
PIPECAT_CLOUD_SERVICE_HOST=<agent-name>.<org-name>
PCC_PUBLIC_KEY=<pipecat public key>
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
JAN_PHONE_NUMBER=
OPENAI_API_KEY=
DEEPGRAM_API_KEY=
CARTESIA_API_KEY=
CARTESIA_VOICE_ID=
SLACK_BOT_TOKEN=
SLACK_CHANNEL_ID=
```

`PCC_PUBLIC_KEY` lets the Twilio webhook request a short-lived authenticated
Pipecat WebSocket URL for each fallback call. Keep `websocket_auth = "token"` in
`pcc-deploy.toml`.

## Deploy

Deploy the Pipecat Cloud agent:

```bash
pipecat cloud auth login
pipecat cloud secrets set <your-secret-set> --file .env
pipecat cloud deploy
```

Before deploying, set `agent_name` and `secret_set` in `pcc-deploy.toml` or pass
them through the Pipecat CLI. The checked-in values are placeholders on purpose.

Deploy the Twilio Function:

```bash
cd twilio-functions
twilio serverless:deploy --env ../.env --load-system-env --functions --no-assets
```

Configure the Twilio phone number voice handler to the deployed Function:

```text
A call comes in: Function
Function Path: /voice
Primary handler fails: blank
Call status changes: blank
Caller Name Lookup: Disabled
```

Do not point the Twilio number directly at Pipecat Cloud. Twilio needs to run the
ring-Jan branch before it falls back to AI.

## Local Development

```bash
uv run uvicorn missed_call_agent.main:app --reload --port 8000
ngrok http 8000
```

For the local FastAPI path, set `PUBLIC_BASE_URL` to the HTTPS ngrok URL and
configure the Twilio number webhook to:

```text
POST https://<PUBLIC_BASE_URL>/voice
```

## Test

Automated checks:

```bash
uv run --extra dev pytest
node --test twilio-functions/test/*.test.js
```

Manual live-call check:

1. Call the Twilio number.
2. Answer Jan's phone and press `1`; the caller should connect to Jan.
3. Call again and do not press `1`, decline, or let it ring.
4. The caller should reach the AI voicemail.
5. Hang up and confirm Slack receives the recap.
