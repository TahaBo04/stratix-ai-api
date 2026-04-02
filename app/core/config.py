"""Application settings for STRATIX AI."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


def _default_database_path() -> str:
    # Vercel Functions cannot write into the deployed project tree, so use /tmp
    # unless an explicit DATABASE_PATH is provided in the project settings.
    if os.getenv("VERCEL"):
        return "/tmp/stratix_ai.db"
    return str(BASE_DIR / "data" / "stratix_ai.db")


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "STRATIX AI API"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    secret_key: str = "change-me"
    database_path: str = _default_database_path()
    datasets_dir: str = str(BASE_DIR / "datasets")
    openai_api_key: str | None = None
    openai_model_primary: str = "gpt-5.4-mini"
    openai_model_fallback: str = "gpt-5.4"
    openai_request_timeout_seconds: int = 30
    openai_max_retries: int = 2
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    default_demo_user_email: str = "demo@stratix.ai"
    default_demo_user_password: str = "demo-password"

    @property
    def database_file(self) -> Path:
        return Path(self.database_path).resolve()

    @property
    def datasets_root(self) -> Path:
        return Path(self.datasets_dir).resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
