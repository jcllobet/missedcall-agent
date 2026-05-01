import pytest
from fastapi.testclient import TestClient

from missed_call_agent.config import get_settings
from missed_call_agent.main import app


def configure_env(monkeypatch):
    values = {
        "PUBLIC_BASE_URL": "https://example.ngrok.app",
        "PIPECAT_CLOUD_SERVICE_HOST": "jan-ai-voicemail.jan-agent-swarm",
        "TWILIO_ACCOUNT_SID": "AC_test",
        "TWILIO_AUTH_TOKEN": "token",
        "TWILIO_PHONE_NUMBER": "+15550000000",
        "JAN_PHONE_NUMBER": "+15551111111",
        "OPENAI_API_KEY": "sk-test",
        "DEEPGRAM_API_KEY": "deepgram-test",
        "CARTESIA_API_KEY": "cartesia-test",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def test_voice_enqueues_caller_and_starts_separate_screening_call(monkeypatch):
    configure_env(monkeypatch)
    started = []

    def fake_start(settings, queue, caller_sid):
        started.append((queue, caller_sid))

    monkeypatch.setattr("missed_call_agent.main.start_jan_screening_call", fake_start)
    client = TestClient(app)

    response = client.post("/voice", data={"From": "+15552222222", "CallSid": "CA_inbound"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert '<Enqueue action="https://example.ngrok.app/voice?queue_result=1"' in response.text
    assert 'waitUrl="https://example.ngrok.app/voice?wait=1"' in response.text
    assert ">jan_CA_inbound</Enqueue>" in response.text
    assert started == [("jan_CA_inbound", "CA_inbound")]


def test_wait_url_leaves_queue_after_timeout(monkeypatch):
    configure_env(monkeypatch)
    client = TestClient(app)

    response = client.post("/voice?wait=1", data={"QueueTime": "10"})

    assert response.status_code == 200
    assert "<Leave" in response.text


def test_wait_url_keeps_caller_isolated_before_timeout(monkeypatch):
    configure_env(monkeypatch)
    client = TestClient(app)

    response = client.post("/voice?wait=1", data={"QueueTime": "2"})

    assert response.status_code == 200
    assert "Trying Jan now" in response.text
    assert "<Leave" not in response.text


def test_call_screen_prompts_jan_to_accept(monkeypatch):
    configure_env(monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/voice?screen=prompt&queue=jan_CA_inbound&caller=CA_inbound",
        data={},
    )

    assert response.status_code == 200
    assert '<Gather action="https://example.ngrok.app/voice?screen=result' in response.text
    assert 'actionOnEmptyResult="true"' in response.text
    assert 'numDigits="1"' in response.text
    assert "Press 1 to accept" in response.text
    assert "<Hangup" in response.text


def test_call_screen_dequeues_caller_when_jan_presses_one(monkeypatch):
    configure_env(monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/voice?screen=result&queue=jan_CA_inbound&caller=CA_inbound",
        data={"Digits": "1"},
    )

    assert response.status_code == 200
    assert "Connecting" in response.text
    assert "<Dial" in response.text
    assert "<Queue>jan_CA_inbound</Queue>" in response.text


@pytest.mark.parametrize(
    ("digits", "reason"),
    [
        pytest.param({}, "jan_not_accepted", id="no-keypress"),
        pytest.param({"Digits": "2"}, "jan_not_accepted", id="wrong-digit"),
    ],
)
def test_call_screen_redirects_caller_to_ai_when_jan_does_not_press_one(
    monkeypatch,
    digits,
    reason,
):
    configure_env(monkeypatch)
    redirected = []

    def fake_redirect(settings, caller_sid, fallback_reason):
        redirected.append((caller_sid, fallback_reason))

    monkeypatch.setattr("missed_call_agent.main.redirect_caller_to_ai", fake_redirect)
    client = TestClient(app)

    response = client.post(
        "/voice?screen=result&queue=jan_CA_inbound&caller=CA_inbound",
        data=digits,
    )

    assert response.status_code == 200
    assert "<Hangup" in response.text
    assert redirected == [("CA_inbound", reason)]


@pytest.mark.parametrize(
    ("call_status", "reason"),
    [
        pytest.param("no-answer", "jan_no_answer", id="person-does-not-pick-up"),
        pytest.param("busy", "jan_busy", id="person-rejects-call"),
        pytest.param("failed", "jan_failed", id="airplane-mode-or-unreachable"),
        pytest.param("canceled", "jan_canceled", id="carrier-cancels-leg"),
    ],
)
def test_failed_jan_screening_call_redirects_caller_to_ai(monkeypatch, call_status, reason):
    configure_env(monkeypatch)
    redirected = []

    def fake_redirect(settings, caller_sid, fallback_reason):
        redirected.append((caller_sid, fallback_reason))

    monkeypatch.setattr("missed_call_agent.main.redirect_caller_to_ai", fake_redirect)
    client = TestClient(app)

    response = client.post(
        "/voice?jan_call_status=1&queue=jan_CA_inbound&caller=CA_inbound",
        data={"CallStatus": call_status},
    )

    assert response.status_code == 200
    assert redirected == [("CA_inbound", reason)]


def test_completed_jan_screening_call_status_does_not_redirect_by_itself(monkeypatch):
    configure_env(monkeypatch)
    redirected = []

    def fake_redirect(settings, caller_sid, fallback_reason):
        redirected.append((caller_sid, fallback_reason))

    monkeypatch.setattr("missed_call_agent.main.redirect_caller_to_ai", fake_redirect)
    client = TestClient(app)

    response = client.post(
        "/voice?jan_call_status=1&queue=jan_CA_inbound&caller=CA_inbound",
        data={"CallStatus": "completed"},
    )

    assert response.status_code == 200
    assert redirected == []


@pytest.mark.parametrize(
    ("answered_by", "reason"),
    [
        pytest.param("machine_start", "jan_machine_start", id="voicemail-greeting-start"),
        pytest.param("machine_end_beep", "jan_machine_end_beep", id="voicemail-beep"),
        pytest.param("machine_end_silence", "jan_machine_end_silence", id="voicemail-silence"),
        pytest.param("machine_end_other", "jan_machine_end_other", id="voicemail-other"),
        pytest.param("fax", "jan_fax", id="fax"),
        pytest.param("unknown", "jan_unknown", id="unknown-not-human"),
    ],
)
def test_amd_non_human_results_redirect_caller_to_ai(monkeypatch, answered_by, reason):
    configure_env(monkeypatch)
    redirected = []

    def fake_redirect(settings, caller_sid, fallback_reason):
        redirected.append((caller_sid, fallback_reason))

    monkeypatch.setattr("missed_call_agent.main.redirect_caller_to_ai", fake_redirect)
    client = TestClient(app)

    response = client.post(
        "/voice?amd_status=1&queue=jan_CA_inbound&caller=CA_inbound",
        data={"AnsweredBy": answered_by},
    )

    assert response.status_code == 200
    assert redirected == [("CA_inbound", reason)]


def test_amd_human_result_does_not_redirect_caller(monkeypatch):
    configure_env(monkeypatch)
    redirected = []

    def fake_redirect(settings, caller_sid, fallback_reason):
        redirected.append((caller_sid, fallback_reason))

    monkeypatch.setattr("missed_call_agent.main.redirect_caller_to_ai", fake_redirect)
    client = TestClient(app)

    response = client.post(
        "/voice?amd_status=1&queue=jan_CA_inbound&caller=CA_inbound",
        data={"AnsweredBy": "human"},
    )

    assert response.status_code == 200
    assert redirected == []


def test_queue_result_streams_to_pipecat_when_not_bridged(monkeypatch):
    configure_env(monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/voice?queue_result=1",
        data={
            "QueueResult": "leave",
            "From": "+15552222222",
            "CallSid": "CA_inbound",
        },
    )

    assert response.status_code == 200
    assert '<Connect><Stream url="wss://api.pipecat.daily.co/ws/twilio">' in response.text
    assert 'name="_pipecatCloudServiceHost" value="jan-ai-voicemail.jan-agent-swarm"' in response.text
    assert 'name="fallback_reason" value="queue_leave"' in response.text
    assert 'name="caller" value="+15552222222"' in response.text


def test_queue_result_hangs_up_after_successful_bridge(monkeypatch):
    configure_env(monkeypatch)
    client = TestClient(app)

    response = client.post("/voice?queue_result=1", data={"QueueResult": "bridged"})

    assert response.status_code == 200
    assert "<Hangup" in response.text
    assert "<Stream" not in response.text


def test_force_ai_streams_to_pipecat(monkeypatch):
    configure_env(monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/voice?force_ai=1&fallback_reason=jan_not_accepted",
        data={"CallSid": "CA_inbound"},
    )

    assert response.status_code == 200
    assert "<Stream" in response.text
    assert 'name="fallback_reason" value="jan_not_accepted"' in response.text
