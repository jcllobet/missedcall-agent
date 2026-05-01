from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from twilio.twiml.voice_response import Connect, Dial, VoiceResponse

from .config import get_settings
from .records import CallRecordStore

app = FastAPI(title="Jan AI Voicemail", version="0.1.0")


def twiml_response(response: VoiceResponse) -> HTMLResponse:
    return HTMLResponse(content=str(response), media_type="application/xml")


def unavailable_twiml(message: str) -> HTMLResponse:
    response = VoiceResponse()
    response.say(message)
    response.hangup()
    return twiml_response(response)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "ok": True,
        "missing_call_control_config": settings.missing_call_control_config(),
        "missing_agent_config": settings.missing_agent_config(),
        "missing_slack_config": settings.missing_slack_config(),
    }


@app.api_route("/voice", methods=["GET", "POST"])
async def voice(request: Request) -> HTMLResponse:
    settings = get_settings()
    missing = settings.missing_call_control_config()
    if missing:
        return unavailable_twiml("Jan's AI voicemail is not configured yet. Please try again later.")

    form = await request.form()
    response = VoiceResponse()
    dial = Dial(
        timeout=settings.human_ring_timeout_seconds,
        action=settings.dial_status_url(),
        method="POST",
        answer_on_bridge=True,
        caller_id=settings.twilio_phone_number,
    )
    dial.number(
        settings.jan_phone_number,
        machine_detection="Enable",
        machine_detection_timeout=5,
        machine_detection_speech_threshold=1500,
        machine_detection_speech_end_threshold=800,
        machine_detection_silence_timeout=3000,
    )
    response.append(dial)
    return twiml_response(response)


@app.api_route("/dial-status", methods=["GET", "POST"])
async def dial_status(request: Request) -> HTMLResponse:
    settings = get_settings()
    missing = settings.missing_call_control_config()
    if missing:
        return unavailable_twiml("Jan's AI voicemail is not configured yet. Please try again later.")

    form = await request.form()
    status = str(form.get("DialCallStatus") or "unknown")
    answered_by = str(form.get("AnsweredBy") or "").lower()
    is_human_answer = status in {"completed", "answered"} and answered_by in {"", "human"}
    if is_human_answer:
        response = VoiceResponse()
        response.hangup()
        return twiml_response(response)

    fallback_reason = (
        f"jan_{answered_by}" if answered_by else f"jan_{status.replace('-', '_')}"
    )
    response = VoiceResponse()
    connect = Connect()
    stream = connect.stream(url=settings.pipecat_cloud_ws_url)
    stream.parameter(name="_pipecatCloudServiceHost", value=settings.pipecat_cloud_service_host or "")
    stream.parameter(name="fallback_reason", value=fallback_reason)
    stream.parameter(name="caller", value=str(form.get("From") or ""))
    stream.parameter(name="inbound_call_sid", value=str(form.get("CallSid") or ""))
    stream.parameter(name="dial_call_sid", value=str(form.get("DialCallSid") or ""))
    response.append(connect)
    return twiml_response(response)


@app.get("/twiml-preview", response_class=Response)
def twiml_preview() -> Response:
    settings = get_settings()
    response = VoiceResponse()
    dial = Dial(
        timeout=settings.human_ring_timeout_seconds,
        action=settings.dial_status_url() or "https://example.com/dial-status",
        method="POST",
        answer_on_bridge=True,
        caller_id=settings.twilio_phone_number or "+15555555555",
    )
    dial.number(settings.jan_phone_number or "+15555555556")
    response.append(dial)
    return Response(content=str(response), media_type="application/xml")


@app.get("/calls")
def list_calls() -> list[dict]:
    settings = get_settings()
    return CallRecordStore(settings.call_output_dir).list()


@app.get("/calls/{call_id}")
def get_call(call_id: str) -> dict:
    settings = get_settings()
    record = CallRecordStore(settings.call_output_dir).get(call_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Call record not found")
    return record
