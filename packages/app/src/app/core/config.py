"""Конфигурация приложения через pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

# Пути к ключам подписи JWT по умолчанию (генерируются командой `make certs`).
_DEFAULT_PRIVATE_KEY = "certs/jwt-private-key.pem"
_DEFAULT_PUBLIC_KEY = "certs/jwt-cert.pem"


class Settings(BaseSettings):
    """Настройки приложения (читаются из .env / переменных окружения)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_algorithm: str = "RS256"
    jwt_expires_minutes: int = 60
    jwt_private_key_path: str = _DEFAULT_PRIVATE_KEY
    jwt_public_key_path: str = _DEFAULT_PUBLIC_KEY


_settings: Settings | None = None


def get_settings() -> Settings:
    """Возвращает единственный экземпляр настроек (кэш)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
