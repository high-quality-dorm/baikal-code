"""Доступ к базе данных: пулы соединений по ролям и RLS-контекст.

Единственный шлюз к PostgreSQL. Приложение не ходит в базу напрямую — только
через db_mcp. Здесь сосредоточена маршрутизация по ролям и установка
Row-Level Security контекста (set_config app.role / app.user_id) в начале
транзакции.

Бизнес-роли (applicant/student/teacher/admin) отображаются на роли PostgreSQL:
    - applicant, student, teacher -> app_ro  (без PII-колонок студентов)
    - admin                        -> app_admin (полный доступ, включая PII)
Запись в журнал аудита идёт через отдельную роль app_audit.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from db_mcp.settings import Settings

# Бизнес-роли приложения (см. docs/roles.md)
APPLICANT = "applicant"
STUDENT = "student"
TEACHER = "teacher"
ADMIN = "admin"

BUSINESS_ROLES = frozenset({APPLICANT, STUDENT, TEACHER, ADMIN})

# Отображение бизнес-роли на ключ пула соединений
_ROLE_TO_POOL = {
    APPLICANT: "ro",
    STUDENT: "ro",
    TEACHER: "ro",
    ADMIN: "admin",
}


class UnknownRoleError(ValueError):
    """Неизвестная бизнес-роль."""


class Pools:
    """Лениво создаваемые пулы соединений asyncpg по ролям PostgreSQL."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pools: dict[str, asyncpg.Pool] = {}

    async def _get(self, key: str, dsn: str) -> asyncpg.Pool:
        """Вернуть пул, создав его при первом обращении."""
        pool = self._pools.get(key)
        if pool is None:
            pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10)
            self._pools[key] = pool
        return pool

    async def ro(self) -> asyncpg.Pool:
        """Пул рабочей роли app_ro (без PII)."""
        return await self._get("ro", self._settings.database_url_ro)

    async def admin(self) -> asyncpg.Pool:
        """Пул роли администрации app_admin (с PII)."""
        return await self._get("admin", self._settings.database_url_admin)

    async def audit(self) -> asyncpg.Pool:
        """Пул роли аудита app_audit (запись в query_log)."""
        return await self._get("audit", self._settings.database_url_audit)

    async def pool_for_role(self, role: str) -> asyncpg.Pool:
        """Пул для бизнес-роли (выбор app_ro/app_admin)."""
        key = _ROLE_TO_POOL.get(role)
        if key is None:
            raise UnknownRoleError(f"Неизвестная роль: {role!r}")
        return await (self.admin() if key == "admin" else self.ro())

    async def close(self) -> None:
        """Закрыть все пулы."""
        for pool in self._pools.values():
            await pool.close()
        self._pools.clear()


@asynccontextmanager
async def connection_for(
    pools: Pools, role: str, user_id: str
) -> AsyncIterator[asyncpg.Connection]:
    """Соединение с установленным RLS-контекстом внутри транзакции.

    Контекст (app.role, app.user_id) задаётся в начале транзакции через
    set_config(..., is_local=true) — эквивалент SET LOCAL, действующий только
    на время её выполнения. Без контекста политики RLS (deny-by-default)
    не пропустят ни одной строки.
    """
    if role not in BUSINESS_ROLES:
        raise UnknownRoleError(f"Неизвестная роль: {role!r}")
    pool = await pools.pool_for_role(role)
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT set_config('app.role', $1, true)", role)
        await conn.execute("SELECT set_config('app.user_id', $1, true)", user_id)
        yield conn
