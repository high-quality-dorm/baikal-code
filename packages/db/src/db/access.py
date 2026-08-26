"""Доступ к базе данных: пулы соединений и RLS-контекст.

Единственный шлюз к PostgreSQL. Приложение не ходит в базу напрямую — только
через пакет `db`. Здесь сосредоточено подключение по двум ролям PostgreSQL
(`app_ro` — доменные запросы, `app_service` — auth/аудит/резолюция identity) и
установка Row-Level Security контекста.

RLS-контекст задаётся двумя независимыми GUC — `app.student_id` и
`app.staff_id` (роль строкой не передаётся, единый user_id не вводится). Скоуп
выводится аддитивно из студенческого и/или кадрового id; гость (нет id) не
получает ни одного GUC — RLS deny-by-default на `students`/`marks`, общие
таблицы открыты без RLS.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from db.models import Identity
from db.settings import Settings


class Pools:
    """Лениво создаваемые пулы соединений asyncpg по ролям PostgreSQL."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pools: dict[str, asyncpg.Pool] = {}
        # Сериализует создание пула: два параллельных первых обращения не
        # должны создать два пула (второй утёк бы).
        self._lock = asyncio.Lock()

    @property
    def statement_timeout_ms(self) -> int:
        """Лимит исполнения одного запроса (мс), применяется в транзакции."""
        return self._settings.statement_timeout_ms

    async def _get(self, key: str, dsn: str) -> asyncpg.Pool:
        """Вернуть пул по ключу, создав его при первом обращении."""
        pool = self._pools.get(key)
        if pool is None:
            async with self._lock:
                pool = self._pools.get(key)
                if pool is None:
                    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10)
                    self._pools[key] = pool
        return pool

    async def ro(self) -> asyncpg.Pool:
        """Пул рабочей роли app_ro (все доменные запросы)."""
        return await self._get("ro", self._settings.database_url_ro)

    async def service(self) -> asyncpg.Pool:
        """Пул служебной роли app_service (auth + аудит + резолюция identity)."""
        return await self._get("service", self._settings.database_url_service)

    async def close(self) -> None:
        """Закрыть все пулы."""
        async with self._lock:
            for pool in self._pools.values():
                await pool.close()
            self._pools.clear()


@asynccontextmanager
async def connection_for(
    pools: Pools, identity: Identity | None
) -> AsyncIterator[asyncpg.Connection]:
    """Соединение с установленным RLS-контекстом внутри транзакции.

    Контекст задаётся в начале транзакции через set_config(..., is_local=true)
    — эквивалент SET LOCAL, действующий только на время её выполнения.

    Для аутентифицированного пользователя ставятся `app.student_id` и/или
    `app.staff_id` (какие заполнены в identity). Для гостя (identity None) ни
    один GUC не ставится: `current_setting(..., true)` вернёт NULL, политики RLS
    (deny-by-default) не пропустят ни одной строки из `students`/`marks`, а
    общие таблицы открыты.

    Также в транзакции задаётся `statement_timeout` (is_local=true): тяжёлый
    запрос не может держать соединение пула дольше заданного лимита.
    """
    pool = await pools.ro()
    async with pool.acquire() as conn, conn.transaction():
        if identity is not None:
            if identity.student_id is not None:
                await conn.execute(
                    "SELECT set_config('app.student_id', $1, true)",
                    str(identity.student_id),
                )
            if identity.staff_id is not None:
                await conn.execute(
                    "SELECT set_config('app.staff_id', $1, true)",
                    str(identity.staff_id),
                )
        await conn.execute(
            "SELECT set_config('statement_timeout', $1, true)",
            str(pools.statement_timeout_ms),
        )
        yield conn
