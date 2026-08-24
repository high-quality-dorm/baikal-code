"""Точка входа FastAPI-приложения."""

from __future__ import annotations

from fastapi import FastAPI

from app.auth.router import _service_dep
from app.auth.router import router as auth_router
from app.services.auth import AuthService
from app.services.providers import InMemoryAuthStore


def build_auth_service() -> AuthService:
    """Собирает сервис auth на in-memory хранилище (до подключения db_mcp)."""
    return AuthService(InMemoryAuthStore())


def create_app() -> FastAPI:
    """Создаёт и настраивает приложение FastAPI."""
    app = FastAPI(title="Baikal")
    app.include_router(auth_router)

    service = build_auth_service()

    def _override() -> AuthService:
        return service

    app.dependency_overrides[_service_dep] = _override
    return app


def main() -> None:
    """Запускает dev-сервер uvicorn (используется console-скриптом `app`)."""
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)


app = create_app()
