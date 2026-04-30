from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    public_base_url: str | None = Field(default=None, alias="PUBLIC_BASE_URL")
    pipecat_cloud_service_host: str | None = Field(default=None, alias="PIPECAT_CLOUD_SERVICE_HOST")
    pipecat_cloud_ws_url: str = Field(
        default="wss://api.pipecat.daily.co/ws/twilio",
        alias="PIPECAT_CLOUD_WS_URL",
    )
    twilio_account_sid: str | None = Field(default=None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str | None = Field(default=None, alias="TWILIO_AUTH_TOKEN")
    twilio_phone_number: str | None = Field(default=None, alias="TWILIO_PHONE_NUMBER")
    jan_phone_number: str | None = Field(default=None, alias="JAN_PHONE_NUMBER")
    human_ring_timeout_seconds: int = Field(default=10, alias="HUMAN_RING_TIMEOUT_SECONDS")
    jan_context_url: str = Field(default="https://www.jcarbonell.com/", alias="JAN_CONTEXT_URL")
    call_recording_mode: str = Field(default="ai_only", alias="CALL_RECORDING_MODE")
    call_output_dir: Path = Field(default=Path("./data/calls"), alias="CALL_OUTPUT_DIR")
    slack_bot_token: str | None = Field(default=None, alias="SLACK_BOT_TOKEN")
    slack_channel_id: str | None = Field(default=None, alias="SLACK_CHANNEL_ID")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    deepgram_api_key: str | None = Field(default=None, alias="DEEPGRAM_API_KEY")
    deepgram_model: str = Field(default="nova-3", alias="DEEPGRAM_MODEL")
    vad_confidence: float = Field(default=0.4, alias="VAD_CONFIDENCE")
    elevenlabs_api_key: str | None = Field(default=None, alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field(default="21m00Tcm4TlvDq8ikWAM", alias="ELEVENLABS_VOICE_ID")
    elevenlabs_model: str = Field(default="eleven_flash_v2_5", alias="ELEVENLABS_MODEL")
    elevenlabs_stability: float = Field(default=0.5, alias="ELEVENLABS_STABILITY")
    elevenlabs_similarity_boost: float = Field(default=0.8, alias="ELEVENLABS_SIMILARITY_BOOST")
    elevenlabs_style: float = Field(default=0.0, alias="ELEVENLABS_STYLE")
    elevenlabs_speed: float = Field(default=1.0, alias="ELEVENLABS_SPEED")
    elevenlabs_use_speaker_boost: bool = Field(default=True, alias="ELEVENLABS_USE_SPEAKER_BOOST")

    def dial_status_url(self) -> str:
        if not self.public_base_url:
            return ""
        return self.public_base_url.rstrip("/") + "/dial-status"

    def missing_call_control_config(self) -> list[str]:
        required = {
            "PUBLIC_BASE_URL": self.public_base_url,
            "TWILIO_PHONE_NUMBER": self.twilio_phone_number,
            "JAN_PHONE_NUMBER": self.jan_phone_number,
            "PIPECAT_CLOUD_SERVICE_HOST": self.pipecat_cloud_service_host,
        }
        return [key for key, value in required.items() if not value]

    def missing_agent_config(self) -> list[str]:
        required = {
            "TWILIO_ACCOUNT_SID": self.twilio_account_sid,
            "TWILIO_AUTH_TOKEN": self.twilio_auth_token,
            "OPENAI_API_KEY": self.openai_api_key,
            "DEEPGRAM_API_KEY": self.deepgram_api_key,
            "ELEVENLABS_API_KEY": self.elevenlabs_api_key,
        }
        return [key for key, value in required.items() if not value]

    def missing_voice_config(self) -> list[str]:
        return self.missing_call_control_config() + self.missing_agent_config()

    def missing_slack_config(self) -> list[str]:
        required = {
            "SLACK_BOT_TOKEN": self.slack_bot_token,
            "SLACK_CHANNEL_ID": self.slack_channel_id,
        }
        return [key for key, value in required.items() if not value]


@lru_cache
def get_settings() -> Settings:
    return Settings()
