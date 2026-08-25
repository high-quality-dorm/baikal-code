"""Настройки подключения к базе данных для db_mcp.

Строки подключения разделены по ролям PostgreSQL (принцип наименьших
привилегий): рабочая роль без PII, роль администрации (с PII) и роль аудита
(запись в query_log). Источник — переменные окружения / `.env`.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from db_mcp.roles import DbPool


class Settings(BaseSettings):
    """Строки подключения ролей приложения к PostgreSQL."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url_ro: str = "postgresql://app_ro:ro_secret@localhost:5432/university"
    database_url_admin: str = (
        "postgresql://app_admin:admin_secret@localhost:5432/university"
    )
    database_url_service: str = (
        "postgresql://app_service:service_secret@localhost:5432/university"
    )
    # Лимит исполнения одного запроса (мс). Ставится в начале транзакции
    # (SET LOCAL): защита от «зависших» SELECT, держащих соединение пула.
    statement_timeout_ms: int = 10_000

    def dsn_for(self, db_pool: DbPool) -> str:
        """Строка подключения для роли PostgreSQL (единая точка)."""
        return {
            DbPool.RO: self.database_url_ro,
            DbPool.ADMIN: self.database_url_admin,
            DbPool.SERVICE: self.database_url_service,
        }[db_pool]


settings = Settings()
