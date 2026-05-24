import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_env: str = "development"
    app_secret_key: str = "change-me-to-a-random-secret-key"
    cors_origins: list[str] = ["http://localhost:8000", "http://localhost:3000"]

    # Database — TimescaleDB
    database_url: str = "postgresql://plana_user:plana_dev_password@localhost:5432/plana"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True

    # Anthropic / Claude API
    anthropic_api_key: str | None = None
    claude_enabled: bool = True

    # Telegram Bot
    telegram_bot_token: str | None = None
    telegram_enabled: bool = False
    telegram_chat_id: int | None = None  # user's chat ID for proactive outreach

    # Garmin Connect
    garmin_email: str | None = None
    garmin_password: str | None = None
    garmin_enabled: bool = False

    # Strava
    strava_client_id: str | None = None
    strava_client_secret: str | None = None
    strava_refresh_token: str | None = None
    strava_enabled: bool = False

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def resolved_database_url(self) -> str:
        return os.environ.get("POSTGRES_URL") or self.database_url

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
