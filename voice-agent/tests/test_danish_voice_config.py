from missed_call_agent.config import DANISH_CARTESIA_VOICE_ID, Settings
from missed_call_agent.prompts import VOICEMAIL_ENDING, VOICEMAIL_GREETING, voicemail_instructions


def test_danish_voice_defaults_and_prompt_accept_danish_characters(monkeypatch) -> None:
    for key in (
        "DEEPGRAM_MODEL",
        "DEEPGRAM_LANGUAGE",
        "CARTESIA_MODEL",
        "CARTESIA_LANGUAGE",
        "CARTESIA_VOICE_ID",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.deepgram_model == "nova-3"
    assert settings.deepgram_language == "da"
    assert settings.cartesia_model == "sonic-3"
    assert settings.cartesia_language == "da"
    assert settings.cartesia_voice_id == DANISH_CARTESIA_VOICE_ID

    prompt = voicemail_instructions(settings)
    assert "only be speaking in Danish" in prompt
    assert "MUST understand Danish" in prompt

    danish_text = VOICEMAIL_GREETING + VOICEMAIL_ENDING
    for char in ("æ", "ø", "å"):
        assert char in danish_text
