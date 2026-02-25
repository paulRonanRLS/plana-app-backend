from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_env: str = "development"
    app_secret_key: str = "change-me-to-a-random-secret-key"
    cors_origins: list[str] = ["http://localhost:8081", "http://localhost:19006"]

    # Database
    database_url: str = "postgresql://recipe_user:recipe_dev_password@localhost:5432/recipe_app"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Firebase Auth (optional for initial development)
    firebase_credentials_path: str | None = None

    # Anthropic / Claude API (optional until extraction is built)
    anthropic_api_key: str | None = None

    # Google Cloud Vision (optional until photo capture is built)
    google_cloud_credentials_path: str | None = None

    # AWS S3 (optional - local storage used by default)
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_s3_bucket: str | None = None
    aws_s3_region: str | None = None

    # File storage
    storage_backend: str = "local"  # "local" or "s3"
    local_upload_dir: str = "./uploads"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
