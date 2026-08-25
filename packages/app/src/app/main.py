"""Точка входа FastAPI-приложения."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.ask import _pipeline_dep
from app.api.ask import router as ask_router
from app.auth.router import _service_dep
from app.auth.router import router as auth_router
from app.core.config import settings
from app.gateway import GatewayClient
from app.llm import ChatLLM
from app.services.auth import AuthService
from app.services.pipeline import Pipeline
from app.services.providers import InMemoryAuthStore


def build_auth_service() -> AuthService:
    """Собирает сервис auth на in-memory хранилище (до подключения db_mcp)."""
    return AuthService(InMemoryAuthStore())


def build_pipeline() -> Pipeline:
    """Собирает конвейер text-to-SQL: MCP-клиент шлюза + LLM."""
    return Pipeline(
        GatewayClient(settings.db_mcp_command),
        ChatLLM(settings),
    )


def create_app() -> FastAPI:
    """Создаёт и настраивает приложение FastAPI."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await pipeline.close()

    app = FastAPI(title="Baikal", lifespan=lifespan)
    app.include_router(auth_router)
    app.include_router(ask_router)

    service = build_auth_service()
    pipeline = build_pipeline()

    def _service_override() -> AuthService:
        return service

    def _pipeline_override() -> Pipeline:
        return pipeline

    app.dependency_overrides[_service_dep] = _service_override
    app.dependency_overrides[_pipeline_dep] = _pipeline_override
    return app


def main() -> None:
    """Запускает dev-сервер uvicorn (используется console-скриптом `app`)."""
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)


app = create_app()
