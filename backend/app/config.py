"""Application configuration, loaded from environment variables / backend/.env."""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "AI Personal Learning & Productivity Hub"
    environment: Literal["development", "production", "test"] = "development"

    # Database — SQLite by default; set a postgresql+psycopg:// URL to migrate later.
    database_url: str = f"sqlite:///{(DATA_DIR / 'hub.db').as_posix()}"

    # Security
    secret_key: str = Field(..., min_length=32, description="JWT signing key")
    encryption_key: str | None = Field(
        None, description="Fernet key used to encrypt stored OAuth tokens"
    )
    access_token_expire_minutes: int = 60 * 24 * 7
    cookie_secure: bool = False

    # URLs
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"

    # Scheduling / automation
    scheduler_mode: Literal["internal", "n8n", "off"] = "internal"
    automation_api_key: str | None = None

    # Email
    email_provider: Literal["none", "smtp", "gmail_api"] = "none"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    email_from: str | None = None
    gmail_client_id: str | None = None
    gmail_client_secret: str | None = None

    # GitHub
    github_client_id: str | None = None
    github_client_secret: str | None = None

    # Anthropic
    youtube_api_key: str | None = None  # YouTube Data API v3 key; backend only, never sent to the browser
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
