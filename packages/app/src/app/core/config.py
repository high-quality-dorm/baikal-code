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

    # OpenAI-совместимый LLM (генерация SQL и пересказ ответа).
    # Значения заполняются вручную в .env при эксплуатации.
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_temperature: float = 0.0

    # Команда запуска шлюза db_mcp (используется MCP-клиентом по stdio).
    db_mcp_command: str = "uv run db-mcp"


settings = Settings()
