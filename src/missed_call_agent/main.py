from collections.abc import Mapping
from typing import Literal
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from twilio.rest import Client
from twilio.twiml.voice_response import Connect, VoiceResponse

from .config import Settings, get_settings
from .records import CallRecordStore

app = FastAPI(title="Jan AI Voicemail", version="0.1.0")
FAILED_JAN_STATUSES = {"busy", "failed", "no-answer", "canceled"}
VoiceEvent = Literal[
    "force_ai",
    "jan_call_status",
    "amd_status",
    "wait",
    "queue_result",
    "screen_prompt",
    "screen_result",
    "initial_call",
]


def twiml_response(response: VoiceResponse) -> HTMLResponse:
    return HTMLResponse(content=str(response), media_type="application/xml")


def unavailable_twiml(message: str) -> HTMLResponse:
    response = VoiceResponse()
    response.say(message)
    response.hangup()
    return twiml_response(response)


def queue_name(call_sid: str | None) -> str:
    """Build the per-call Twilio queue name.

    Args:
        call_sid: Inbound Twilio call SID.
    Returns:
        A Twilio-safe queue name for the parked caller.
    """
    safe = "".join(
        char if char.isalnum() or char == "_" else "_" for char in str(call_sid or "call")
    )
    return f"jan_{safe}"[:64]


def voice_url(settings: Settings, **params: str) -> str:
    """Build a public /voice callback URL.

    Args:
        settings: Runtime settings containing PUBLIC_BASE_URL.
        **params: Query params for the callback route.
    Returns:
        Absolute /voice URL with encoded params.
    """
    return settings.voice_url(urlencode(params))


def ai_stream_twiml(
    settings: Settings,
    form: Mapping[str, object],
    fallback_reason: str,
) -> HTMLResponse:
    """Return TwiML that connects the caller to Pipecat.

    Args:
        settings: Runtime settings with Pipecat stream config.
        form: Twilio webhook payload used for caller/call metadata.
        fallback_reason: Reason label passed to the AI agent.
    Returns:
        XML response containing <Connect><Stream>.
    """
    response = VoiceResponse()
    connect = Connect()
    stream = connect.stream(url=settings.pipecat_cloud_ws_url)
    stream.parameter(name="_pipecatCloudServiceHost", value=settings.pipecat_cloud_service_host or "")
    stream.parameter(name="fallback_reason", value=fallback_reason)
    stream.parameter(name="caller", value=str(form.get("From") or ""))
    stream.parameter(name="inbound_call_sid", value=str(form.get("CallSid") or form.get("caller") or ""))
    stream.parameter(name="dial_call_sid", value=str(form.get("DialCallSid") or ""))
    response.append(connect)
    return twiml_response(response)


def start_jan_screening_call(settings: Settings, queue: str, caller_sid: str) -> None:
    """Start the separate outbound call that asks Jan to accept.

    Args:
        settings: Runtime settings with Twilio credentials and phone numbers.
        queue: Queue holding the original caller.
        caller_sid: Original caller CallSid to redirect on fallback.
    Returns:
        None.
    """
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise RuntimeError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are required")

    Client(settings.twilio_account_sid, settings.twilio_auth_token).calls.create(
        to=settings.jan_phone_number,
        from_=settings.twilio_phone_number,
        url=voice_url(settings, screen="prompt", queue=queue, caller=caller_sid),
        method="POST",
        timeout=settings.human_ring_timeout_seconds,
        status_callback=voice_url(settings, jan_call_status="1", queue=queue, caller=caller_sid),
        status_callback_method="POST",
        status_callback_event=["completed"],
        machine_detection="Enable",
        async_amd=True,
        async_amd_status_callback=voice_url(settings, amd_status="1", queue=queue, caller=caller_sid),
        async_amd_status_callback_method="POST",
    )


def redirect_caller_to_ai(settings: Settings, caller_sid: str, fallback_reason: str) -> None:
    """Redirect a parked caller to the AI stream.

    Args:
        settings: Runtime settings with Twilio credentials and base URL.
        caller_sid: Original caller CallSid to update.
        fallback_reason: Reason label passed to the AI agent.
    Returns:
        None.
    """
    if not caller_sid or not settings.twilio_account_sid or not settings.twilio_auth_token:
        return

    Client(settings.twilio_account_sid, settings.twilio_auth_token).calls(caller_sid).update(
        url=voice_url(settings, force_ai="1", fallback_reason=fallback_reason),
        method="POST",
    )


def voice_event(query: Mapping[str, str], form: Mapping[str, object]) -> VoiceEvent:
    """Classify the /voice webhook into one call-control state.

    Args:
        query: URL query params from Twilio callback URLs.
        form: Twilio webhook form payload.
    Returns:
        The state handler name for this webhook.
    """
    if query.get("force_ai") == "1":
        return "force_ai"
    if query.get("jan_call_status") == "1":
        return "jan_call_status"
    if query.get("amd_status") == "1":
        return "amd_status"
    if query.get("wait") == "1":
        return "wait"
    if query.get("queue_result") == "1" or form.get("QueueResult"):
        return "queue_result"
    if query.get("screen") == "prompt":
        return "screen_prompt"
    if query.get("screen") == "result":
        return "screen_result"
    return "initial_call"


def empty_twiml() -> HTMLResponse:
    return twiml_response(VoiceResponse())


def handle_jan_call_status(
    settings: Settings,
    query: Mapping[str, str],
    form: Mapping[str, object],
) -> HTMLResponse:
    call_status = str(form.get("CallStatus") or "").lower()
    if call_status in FAILED_JAN_STATUSES:
        redirect_caller_to_ai(
            settings,
            query.get("caller") or "",
            f"jan_{call_status.replace('-', '_')}",
        )
    return empty_twiml()


def handle_amd_status(
    settings: Settings,
    query: Mapping[str, str],
    form: Mapping[str, object],
) -> HTMLResponse:
    answered_by = str(form.get("AnsweredBy") or "").lower()
    if answered_by and answered_by != "human":
        redirect_caller_to_ai(settings, query.get("caller") or "", f"jan_{answered_by}")
    return empty_twiml()


def handle_queue_wait(settings: Settings, form: Mapping[str, object]) -> HTMLResponse:
    queue_time = int(form.get("QueueTime") or 0)
    response = VoiceResponse()
    if queue_time >= settings.ai_failsafe_wait_seconds:
        response.leave()
    else:
        response.say("Trying Jan now.")
        response.pause(length=5)
    return twiml_response(response)


def handle_queue_result(settings: Settings, form: Mapping[str, object]) -> HTMLResponse:
    queue_result = str(form.get("QueueResult") or "timeout")
    if queue_result == "bridged":
        response = VoiceResponse()
        response.hangup()
        return twiml_response(response)
    return ai_stream_twiml(settings, form, f"queue_{queue_result}")


def handle_screen_prompt(settings: Settings, query: Mapping[str, str]) -> HTMLResponse:
    queue = query.get("queue") or ""
    caller = query.get("caller") or ""
    response = VoiceResponse()
    gather = response.gather(
        action=voice_url(settings, screen="result", queue=queue, caller=caller),
        method="POST",
        num_digits=1,
        timeout=6,
        input="dtmf",
        action_on_empty_result=True,
    )
    gather.say("Call for Jan. Press 1 to accept.")
    response.hangup()
    return twiml_response(response)


def handle_screen_result(
    settings: Settings,
    query: Mapping[str, str],
    form: Mapping[str, object],
) -> HTMLResponse:
    queue = query.get("queue") or ""
    caller = query.get("caller") or ""
    response = VoiceResponse()
    if form.get("Digits") == "1":
        response.say("Connecting.")
        dial = response.dial(
            timeout=5,
            action=voice_url(settings, agent_done="1", queue=queue),
            method="POST",
        )
        dial.queue(queue)
        return twiml_response(response)

    redirect_caller_to_ai(settings, caller, "jan_not_accepted")
    response.hangup()
    return twiml_response(response)


def handle_initial_call(settings: Settings, form: Mapping[str, object]) -> HTMLResponse:
    caller_sid = str(form.get("CallSid") or "")
    queue = queue_name(caller_sid)
    start_jan_screening_call(settings, queue, caller_sid)

    response = VoiceResponse()
    response.enqueue(
        queue,
        action=settings.voice_url("queue_result=1"),
        method="POST",
        wait_url=settings.voice_url("wait=1"),
        wait_url_method="POST",
    )
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

    form = dict(await request.form())
    query = request.query_params

    match voice_event(query, form):
        case "force_ai":
            return ai_stream_twiml(
                settings,
                form,
                query.get("fallback_reason") or "jan_not_accepted",
            )
        case "jan_call_status":
            return handle_jan_call_status(settings, query, form)
        case "amd_status":
            return handle_amd_status(settings, query, form)
        case "wait":
            return handle_queue_wait(settings, form)
        case "queue_result":
            return handle_queue_result(settings, form)
        case "screen_prompt":
            return handle_screen_prompt(settings, query)
        case "screen_result":
            return handle_screen_result(settings, query, form)
        case "initial_call":
            return handle_initial_call(settings, form)


@app.get("/twiml-preview", response_class=Response)
def twiml_preview() -> Response:
    settings = get_settings()
    response = VoiceResponse()
    response.enqueue(
        "jan_CA_preview",
        action=settings.voice_url("queue_result=1") or "https://example.com/voice?queue_result=1",
        method="POST",
        wait_url=settings.voice_url("wait=1") or "https://example.com/voice?wait=1",
        wait_url_method="POST",
    )
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
