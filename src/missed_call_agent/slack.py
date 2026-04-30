import httpx

from .records import CallRecord


def render_slack_recap(record: CallRecord, record_ref: str | None = None) -> dict:
    action_items = "\n".join(f"- {item}" for item in record.action_items) or "- None captured"
    transcript_ref = record_ref or "Stored locally"
    text = f"New AI voicemail from {record.caller_number or 'unknown caller'}"

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "New AI voicemail"}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Caller:*\n{record.caller_number or 'Unknown'}"},
                {"type": "mrkdwn", "text": f"*When:*\n{record.started_at}"},
                {"type": "mrkdwn", "text": f"*Call SID:*\n{record.room_name or 'Unknown'}"},
                {"type": "mrkdwn", "text": f"*Fallback:*\n{record.fallback_reason or 'missed'}"},
            ],
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Summary:*\n{record.summary or 'No summary yet.'}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Action items for Jan:*\n{action_items}"}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Transcript: {transcript_ref}"}]},
    ]
    if record.recording_ref:
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Recording: {record.recording_ref}"}]}
        )
    return {"text": text, "blocks": blocks}


async def post_slack_recap(token: str, channel_id: str, record: CallRecord, record_ref: str | None) -> str:
    payload = {"channel": channel_id, **render_slack_recap(record, record_ref)}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post("https://slack.com/api/chat.postMessage", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack chat.postMessage failed: {data.get('error', 'unknown_error')}")
    return data["ts"]
