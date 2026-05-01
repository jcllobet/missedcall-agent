import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CallRecord:
    id: str = field(default_factory=lambda: f"call_{uuid4().hex}")
    caller_number: str | None = None
    room_name: str | None = None
    started_at: str = field(default_factory=utc_now)
    ended_at: str | None = None
    fallback_reason: str | None = None
    transcript: list[dict[str, str]] = field(default_factory=list)
    summary: str | None = None
    action_items: list[str] = field(default_factory=list)
    recording_ref: str | None = None
    slack_ts: str | None = None


class CallRecordStore:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save(self, record: CallRecord) -> Path:
        path = self.output_dir / f"{record.id}.json"
        path.write_text(json.dumps(asdict(record), indent=2), encoding="utf-8")
        return path

    def list(self) -> list[dict]:
        records = []
        for path in sorted(self.output_dir.glob("call_*.json"), reverse=True):
            records.append(json.loads(path.read_text(encoding="utf-8")))
        return records

    def get(self, call_id: str) -> dict | None:
        path = self.output_dir / f"{call_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


def summarize_transcript_placeholder(transcript: list[dict[str, str]]) -> tuple[str, list[str]]:
    """Local fallback until the OpenAI call-summary pass is wired to real env."""
    caller_lines = [item["text"] for item in transcript if item.get("speaker") == "caller"]
    if not caller_lines:
        return "Caller reached Jan's AI voicemail, but no caller details were captured.", []
    first = caller_lines[0][:240]
    return f"Caller said: {first}", ["Review transcript and follow up if needed."]
