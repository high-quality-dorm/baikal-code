"""Контейнер сервисов приложения и единая точка DI.

Один `AppContext` собирается в `create_app` и инжектится в зависимости
(роутеры, auth-депы) через `get_context`. Тесты переопределяют `get_context`
фейковым контекстом — это единственный шов инъекции.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from db.gateway import Gateway
from fastapi import Depends

from app.services.auth import AuthService
from app.services.pipeline import Pipeline


@dataclass
class AppContext:
    """Единый контейнер сервисов: один Gateway на всё приложение."""

    gateway: Gateway
    auth: AuthService
    pipeline: Pipeline


def get_context() -> AppContext:
    """Возвращает контейнер; переопределяется в create_app и в тестах."""
    raise NotImplementedError


Context = Annotated[AppContext, Depends(get_context)]
