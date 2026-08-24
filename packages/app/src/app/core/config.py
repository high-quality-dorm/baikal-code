"""Конфигурация приложения через pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения (читаются из .env / переменных окружения)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60


_settings: Settings | None = None


def get_settings() -> Settings:
    """Возвращает единственный экземпляр настроек (кэш)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
