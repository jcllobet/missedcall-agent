# missedcall-agent

This repo is split by agent type:

- `voice-agent/`: the current Twilio + Pipecat Cloud voicemail agent.
- `text-agent/`: reserved for the future text agent.

Use the voice agent from its folder:

```bash
cd voice-agent
uv sync --extra dev
uv run --extra dev pytest
```

The voice app can read `.env` from either the repo root or `voice-agent/`.
