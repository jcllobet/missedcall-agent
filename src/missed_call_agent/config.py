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
    ai_failsafe_wait_seconds: int = Field(default=10, alias="AI_FAILSAFE_WAIT_SECONDS")
    jan_context_url: str = Field(default="https://www.jcarbonell.com/", alias="JAN_CONTEXT_URL")
    call_recording_mode: str = Field(default="ai_only", alias="CALL_RECORDING_MODE")
    call_output_dir: Path = Field(default=Path("./data/calls"), alias="CALL_OUTPUT_DIR")
    slack_bot_token: str | None = Field(default=None, alias="SLACK_BOT_TOKEN")
    slack_channel_id: str | None = Field(default=None, alias="SLACK_CHANNEL_ID")
    slack_log_channel_id: str | None = Field(default=None, alias="SLACK_LOG_CHANNEL_ID")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    deepgram_api_key: str | None = Field(default=None, alias="DEEPGRAM_API_KEY")
    deepgram_model: str = Field(default="nova-3", alias="DEEPGRAM_MODEL")
    cartesia_api_key: str | None = Field(default=None, alias="CARTESIA_API_KEY")
    cartesia_voice_id: str = Field(
        default="62ae83ad-4f6a-430b-af41-a9bede9286ca",
        alias="CARTESIA_VOICE_ID",
    )
    cartesia_model: str = Field(default="sonic-3", alias="CARTESIA_MODEL")

    def voice_url(self, query: str = "") -> str:
        if not self.public_base_url:
            return ""
        suffix = "/voice"
        if query:
            suffix += "?" + query.lstrip("?")
        return self.public_base_url.rstrip("/") + suffix

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
            "CARTESIA_API_KEY": self.cartesia_api_key,
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
