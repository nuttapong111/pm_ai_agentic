from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_database_url(url: str) -> str:
    """Railway gives postgres:// — SQLAlchemy async needs postgresql+asyncpg://"""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://localhost/pm_assistant"
    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    line_liff_id: str = ""
    app_encryption_key: str = "dev-encryption-key-change-in-prod!!"
    jwt_secret: str = "dev-jwt-secret"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    app_env: str = "development"
    app_base_url: str = "http://localhost:8000"
    confirmation_timeout_minutes: int = 30

    tracker_adapter: str = "mock"
    email_adapter: str = "mock"
    calendar_adapter: str = "mock"

    google_client_id: str = ""
    google_client_secret: str = ""
    jira_client_id: str = ""
    jira_client_secret: str = ""
    clickup_client_id: str = ""
    clickup_client_secret: str = ""

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_db_url(cls, v: str) -> str:
        return _normalize_database_url(v) if isinstance(v, str) else v


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_yaml_config() -> dict:
    path = Path(__file__).resolve().parent.parent / "config.yaml"
    if path.exists():
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}
