from missed_call_agent.records import CallRecord
from missed_call_agent.slack import render_slack_recap


def test_slack_recap_contains_core_fields():
    record = CallRecord(
        caller_number="+15551234567",
        room_name="call-test",
        fallback_reason="jan_no_answer",
        summary="Caller wants to discuss a project.",
        action_items=["Follow up tomorrow."],
    )

    payload = render_slack_recap(record, "/tmp/call.json")

    assert payload["text"] == "New AI voicemail from +15551234567"
    block_text = str(payload["blocks"])
    assert "Caller wants to discuss a project." in block_text
    assert "Follow up tomorrow." in block_text
    assert "/tmp/call.json" in block_text

