"""Application configuration (Pydantic Settings)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings. No secrets committed to the repo."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://trumporacle:trumporacle@127.0.0.1:5432/trumporacle",
        validation_alias="DATABASE_URL",
    )
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(
        default="claude-haiku-4-5",
        validation_alias="ANTHROPIC_MODEL",
    )
    telegram_api_id: int | None = Field(default=None, validation_alias="TELEGRAM_API_ID")
    telegram_api_hash: str | None = Field(default=None, validation_alias="TELEGRAM_API_HASH")
    artifacts_dir: str = Field(default="artifacts", validation_alias="ARTIFACTS_DIR")
    mlflow_tracking_uri: str = Field(
        default="file:./mlruns",
        validation_alias="MLFLOW_TRACKING_URI",
    )
    discord_webhook_url: str | None = Field(default=None, validation_alias="DISCORD_WEBHOOK_URL")
    log_json: bool = Field(default=False, validation_alias="LOG_JSON")
    truth_social_rss_url: str | None = Field(default=None, validation_alias="TRUTH_SOCIAL_RSS_URL")

    @field_validator(
        "anthropic_api_key",
        "telegram_api_id",
        "telegram_api_hash",
        "discord_webhook_url",
        "truth_social_rss_url",
        mode="before",
    )
    @classmethod
    def empty_env_as_none(cls, v: object) -> object:
        """``.env`` often sets ``KEY=`` with no value → empty string; treat as unset."""

        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, v: object) -> object:
        """Accept Neon/Heroku-style ``postgres://`` and bare ``postgresql://`` URLs."""

        if not isinstance(v, str):
            return v
        s = v.strip()
        if s.startswith("postgres://"):
            return "postgresql+psycopg://" + s[len("postgres://") :]
        scheme, sep, rest = s.partition("://")
        if sep and "+" not in scheme and scheme in {"postgresql", "postgres"}:
            return f"postgresql+psycopg://{rest}"
        return s


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()
