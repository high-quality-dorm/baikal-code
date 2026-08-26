"""Точка входа FastAPI-приложения."""

from __future__ import annotations

from contextlib import asynccontextmanager

from db.gateway import Gateway
from fastapi import FastAPI

from app.api.ask import router as ask_router
from app.auth.router import router as auth_router
from app.context import AppContext, get_context
from app.core.config import settings
from app.llm import ChatLLM
from app.services.auth import AuthService
from app.services.pipeline import Pipeline


def create_app() -> FastAPI:
    """Создаёт приложение: общий Gateway + сервисы auth и pipeline.

    `get_context` переопределяется единожды — это единственный шов DI
    (в тестах подменяется фейковым контекстом).
    """
    gateway = Gateway()
    context = AppContext(
        gateway=gateway,
        auth=AuthService(gateway),
        pipeline=Pipeline(gateway, ChatLLM(settings)),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await gateway.close()

    app = FastAPI(title="Baikal", lifespan=lifespan)
    app.include_router(auth_router)
    app.include_router(ask_router)
    app.dependency_overrides[get_context] = lambda: context
    return app


def main() -> None:
    """Запускает dev-сервер uvicorn (используется console-скриптом `app`)."""
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)


app = create_app()
