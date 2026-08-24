"""Настройки подключения к базе данных для db_mcp.

Строки подключения разделены по ролям PostgreSQL (принцип наименьших
привилегий): рабочая роль без PII, роль администрации (с PII) и роль аудита
(запись в query_log). Источник — переменные окружения / `.env`.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Строки подключения ролей приложения к PostgreSQL."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url_ro: str = "postgresql://app_ro:ro_secret@localhost:5432/university"
    database_url_admin: str = (
        "postgresql://app_admin:admin_secret@localhost:5432/university"
    )
    database_url_audit: str = (
        "postgresql://app_audit:audit_secret@localhost:5432/university"
    )


settings = Settings()
