"""Настройки подключения к базе данных.

Две роли PostgreSQL (принцип наименьших привилегий): рабочая read-only роль
`app_ro` (все доменные запросы, скоуп строк задаёт RLS) и служебная роль
`app_service` (auth, аудит, резолюция identity). Роль `app_admin` отсутствует —
доступ администратора обеспечивает политика RLS (`staff.position = 'admin'`).

Источник — переменные окружения / `.env`.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Строки подключения ролей приложения к PostgreSQL."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url_ro: str = "postgresql://app_ro:ro_secret@localhost:5432/university"
    database_url_service: str = (
        "postgresql://app_service:service_secret@localhost:5432/university"
    )
    # Лимит исполнения одного запроса (мс). Ставится в начале транзакции
    # (SET LOCAL): защита от «зависших» SELECT, держащих соединение пула.
    statement_timeout_ms: int = 10_000


settings = Settings()
