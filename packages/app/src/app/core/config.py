"""Конфигурация приложения через pydantic-settings."""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Dev-дефолт только для локальной разработки; в проде всегда задавать свой
# сильный секрет (JWT_SECRET в .env). Длина >= 32 байта обязательна для HS256.
_DEV_JWT_SECRET = "dev-only-change-me-use-strong-random-secret-0123456789"


class Settings(BaseSettings):
    """Настройки приложения (читаются из .env / переменных окружения)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = _DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_must_be_long(cls, v: str) -> str:
        if len(v.encode("utf-8")) < 32:
            raise ValueError(
                "jwt_secret must be at least 32 bytes for HS256 (use a strong random value)"
            )
        return v


_settings: Settings | None = None


def get_settings() -> Settings:
    """Возвращает единственный экземпляр настроек (кэш)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
