# missedcall-agent

Jan AI Voicemail: inbound callers ring Jan first through Twilio. Jan must press
`1` to accept the call. If Jan does not answer, does not press `1`, declines, or
the phone goes straight to carrier voicemail, Twilio sends the still-active
caller to a Pipecat Cloud voice bot and the bot sends Jan a Slack recap.

## Architecture

```text
Caller
  |
  v
Twilio number
  |
  v
Call-control /voice
  |
  v
Caller is parked in Twilio <Enqueue>
  |
  | separate outbound call
  v
Jan leg gets private /voice?screen=prompt
  | press 1                         | no answer / no keypress / voicemail / busy / failed
  v                                 v
<Dial><Queue> dequeues caller       Caller stays isolated in queue
  |                                 |
  v                                 v
Caller bridges to Jan               Queue leaves to /voice?queue_result=1
                                    |
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

- `twilio-functions/functions/voice.js`: Twilio-hosted call-control Function.
- `src/missed_call_agent/main.py`: FastAPI mirror for local testing or external hosting.
- `bot.py`: Pipecat Cloud agent entrypoint.
- `Dockerfile`: Pipecat Cloud agent image.
- `Dockerfile.web`: optional FastAPI call-control image if hosting it in a container.
- `pcc-deploy.toml`: Pipecat Cloud deployment config.

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
AI_FAILSAFE_WAIT_SECONDS=10
OPENAI_API_KEY=
DEEPGRAM_API_KEY=
CARTESIA_API_KEY=
SLACK_BOT_TOKEN=
SLACK_CHANNEL_ID=
```

`PUBLIC_BASE_URL` is the HTTPS URL where Twilio can reach the FastAPI
call-control app. It is only required for the FastAPI/ngrok path. Twilio
Functions can use relative URLs and do not need it for call routing.

For local FastAPI testing, use ngrok:

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

## Twilio Function Setup

The Twilio-hosted Function is the simplest production call-control setup. In
Twilio Console, create or open a Functions Service named:

```text
jan-ai-voicemail-call-control
```

Create a Function at this path and paste the contents of
`twilio-functions/functions/voice.js`:

```text
/voice
```

Set these Twilio Function environment variables:

```text
PIPECAT_CLOUD_SERVICE_HOST=jan-ai-voicemail.jan-agent-swarm
PIPECAT_CLOUD_WS_URL=wss://api.pipecat.daily.co/ws/twilio
TWILIO_PHONE_NUMBER=<your Twilio number>
JAN_PHONE_NUMBER=<Jan's real phone number>
HUMAN_RING_TIMEOUT_SECONDS=10
AI_FAILSAFE_WAIT_SECONDS=10
```

Save the Function, deploy the Service, and note the Environment you deployed to,
for example `dev-environment`.

## Twilio Number Setup

For the Twilio phone number Voice Configuration, use the Function you deployed:

```text
Configure with:
Webhook, TwiML Bin, Function, Studio Flow, Proxy Service

A call comes in: Function
Service: jan-ai-voicemail-call-control
Environment: dev-environment
Function Path: /voice

Primary handler fails: blank
Call status changes: blank
Caller Name Lookup: Disabled
```

You do not need a Twilio phone-number level TwiML Bin for this setup. The
Function returns the TwiML dynamically.
You also do not need the phone-number level "Call status changes" webhook; the
Function receives queue and screening events through `/voice`.

For the local FastAPI/ngrok alternative, configure the Twilio phone number with
a webhook instead:

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

The `/voice` function also handles Jan's private accept prompt at
`/voice?screen=prompt` and `/voice?screen=result`. No Twilio number routing
setting should point directly at those URLs; the initial `/voice` webhook starts
the separate Jan screening call.

## Generated TwiML Shape

Initial `/voice` response:

```xml
<Response>
  <Enqueue action="/voice?queue_result=1" method="POST" waitUrl="/voice?wait=1" waitUrlMethod="POST">
    jan_CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  </Enqueue>
</Response>
```

At the same time, the Function starts a separate outbound call to Jan using the
Twilio REST API with Answering Machine Detection enabled:

```text
to: JAN_PHONE_NUMBER
from: TWILIO_PHONE_NUMBER
url: https://<function-domain>/voice?screen=prompt&queue=jan_CA...&caller=CA...
timeout: HUMAN_RING_TIMEOUT_SECONDS
machineDetection: Enable
asyncAmd: true
asyncAmdStatusCallback: https://<function-domain>/voice?amd_status=1&queue=jan_CA...&caller=CA...
```

Jan's private `/voice?screen=prompt` response:

```xml
<Response>
  <Gather action="/voice?screen=result&amp;queue=jan_CA...&amp;caller=CA..." method="POST" numDigits="1" timeout="6" input="dtmf" actionOnEmptyResult="true">
    <Say>Call for Jan. Press 1 to accept.</Say>
  </Gather>
  <Hangup/>
</Response>
```

If Jan presses `1`, the Jan leg dequeues the caller:

```xml
<Response>
  <Say>Connecting.</Say>
  <Dial timeout="5" action="/voice?agent_done=1&amp;queue=jan_CA..." method="POST">
    <Queue>jan_CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx</Queue>
  </Dial>
</Response>
```

If Jan does not press `1`, the Function redirects the queued caller to:

```xml
<Response>
  <Connect>
    <Stream url="wss://api.pipecat.daily.co/ws/twilio">
      <Parameter name="_pipecatCloudServiceHost" value="jan-ai-voicemail.jan-agent-swarm"/>
      <Parameter name="fallback_reason" value="jan_no_answer"/>
    </Stream>
  </Connect>
</Response>
```

The failsafe rule is: the caller is never placed on Jan's phone leg. Jan's
carrier voicemail can only answer the separate Jan screening call. The original
caller remains isolated in the Twilio queue until Jan presses `1`; otherwise the
queue leaves to the AI stream after `AI_FAILSAFE_WAIT_SECONDS` or immediately
after an empty/wrong screening result, rejected call, busy signal, failed call,
no-answer status, or AMD result other than `AnsweredBy=human` from Jan's
separate screening call.

## Test

1. Deploy the Pipecat Cloud agent.
2. Deploy the Twilio Function Service with `/voice`.
3. Configure the Twilio number to call the `/voice` Function.
4. Call the Twilio number.
5. Answer Jan's phone and press `1`; confirm the caller connects to Jan.
6. Call again and do not press `1`, or let Jan's carrier voicemail answer.
7. Confirm the caller hears the AI voicemail.
8. Hang up and confirm Slack receives a recap.

If Jan answers but does not press `1`, the caller should not connect to Jan and
should fall through to AI voicemail.

## Useful FastAPI Endpoints

- `GET /health`: missing configuration check.
- `POST /voice`: Twilio inbound call webhook.
- `GET /twiml-preview`: preview the initial ring-Jan TwiML.

## Local Verification

```bash
uv run --extra dev pytest
node --test twilio-functions/test/*.test.js
```

## Legacy LiveKit Files

The old LiveKit deployment files are archived under `archive/livekit/` only for
reference. The active agent runtime is Pipecat Cloud.
