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
from app.services.providers import DbUserCredentialsStore, UserCredentialsStore


def build_auth_service(
    auth_store: UserCredentialsStore | None = None,
) -> tuple[AuthService, GatewayClient | None]:
    """Собирает сервис auth на реальном хранилище учёток через шлюз db_mcp.

    Возвращает (сервис, gateway-клиент) — клиент закрывается в lifespan. Если
    передан готовый auth_store (например, InMemoryAuthStore в тестах), шлюз не
    создаётся и возвращается None. Отдельный GatewayClient от конвейера:
    у auth и pipeline независимые жизненные циклы MCP-сессии.
    """
    if auth_store is not None:
        return AuthService(auth_store), None
    gateway = GatewayClient(settings.db_mcp_command)
    service = AuthService(DbUserCredentialsStore(gateway))
    return service, gateway


def build_pipeline() -> Pipeline:
    """Собирает конвейер text-to-SQL: MCP-клиент шлюза + LLM."""
    return Pipeline(
        GatewayClient(settings.db_mcp_command),
        ChatLLM(settings),
    )


def create_app(auth_store: UserCredentialsStore | None = None) -> FastAPI:
    """Создаёт и настраивает приложение FastAPI.

    auth_store — опциональное хранилище учёток для инъекции в тестах; по
    умолчанию используется реальное хранилище через шлюз db_mcp.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await pipeline.close()
        if auth_gateway is not None:
            await auth_gateway.close()

    app = FastAPI(title="Baikal", lifespan=lifespan)
    app.include_router(auth_router)
    app.include_router(ask_router)

    service, auth_gateway = build_auth_service(auth_store)
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
