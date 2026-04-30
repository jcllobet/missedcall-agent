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
        "ELEVENLABS_API_KEY": "elevenlabs-test",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def test_voice_twiml_dials_jan(monkeypatch):
    configure_env(monkeypatch)
    client = TestClient(app)

    response = client.post("/voice", data={"From": "+15552222222", "CallSid": "CA_inbound"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert '<Dial action="https://example.ngrok.app/dial-status"' in response.text
    assert 'answerOnBridge="true"' in response.text
    assert '<Number>+15551111111</Number>' in response.text


def test_dial_status_streams_to_pipecat_on_no_answer(monkeypatch):
    configure_env(monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/dial-status",
        data={
            "DialCallStatus": "no-answer",
            "From": "+15552222222",
            "CallSid": "CA_inbound",
            "DialCallSid": "CA_dial",
        },
    )

    assert response.status_code == 200
    assert '<Connect><Stream url="wss://api.pipecat.daily.co/ws/twilio">' in response.text
    assert 'name="_pipecatCloudServiceHost" value="jan-ai-voicemail.jan-agent-swarm"' in response.text
    assert 'name="fallback_reason" value="jan_no_answer"' in response.text
    assert 'name="caller" value="+15552222222"' in response.text


def test_dial_status_hangs_up_after_completed_human_call(monkeypatch):
    configure_env(monkeypatch)
    client = TestClient(app)

    response = client.post("/dial-status", data={"DialCallStatus": "completed"})

    assert response.status_code == 200
    assert "<Hangup" in response.text
    assert "<Stream" not in response.text
