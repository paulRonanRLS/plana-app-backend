import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_env: str = "development"
    app_secret_key: str = "change-me-to-a-random-secret-key"
    cors_origins: list[str] = ["http://localhost:8081", "http://localhost:19006"]

    # Database — Railway injects POSTGRES_URL; fall back to local default
    database_url: str = "postgresql://recipe_user:recipe_dev_password@localhost:5432/recipe_app"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True

    # Firebase Auth
    firebase_enabled: bool = False
    firebase_credentials_json: str | None = None  # full service account JSON as string (for Railway)
    firebase_project_id: str = "rls-recipe"
    firebase_web_api_key: str | None = None
    firebase_test_email: str | None = None
    firebase_test_password: str | None = None

    # Anthropic / Claude API
    anthropic_api_key: str | None = None
    claude_enabled: bool = True

    # Google Cloud Vision
    google_cloud_credentials_path: str | None = None
    google_application_credentials: str | None = None
    google_cloud_enabled: bool = False

    # Google Cloud Storage
    use_gcs: bool = False
    gcs_bucket_name: str | None = None

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def resolved_database_url(self) -> str:
        """
        Returns the correct database URL for the current environment.
        Checks POSTGRES_URL first (Railway's managed variable name),
        then falls back to DATABASE_URL / the pydantic default.
        """
        return os.environ.get("POSTGRES_URL") or self.database_url

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
