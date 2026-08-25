"""Доступ к базе данных: пулы соединений по ролям и RLS-контекст.

Единственный шлюз к PostgreSQL. Приложение не ходит в базу напрямую — только
через db_mcp. Здесь сосредоточена маршрутизация по ролям и установка
Row-Level Security контекста (set_config app.role / app.user_id) в начале
транзакции.

Бизнес-роли (applicant/student/teacher/admin) отображаются на роли PostgreSQL
через единый словарь `_BUSINESS_ROLE_TO_POOL`:
    - applicant, student, teacher -> app_ro  (без PII-колонок студентов)
    - admin                        -> app_admin (полный доступ, включая PII)
Запись в журнал аудита идёт через отдельную роль app_audit.
Канонический вокабуляр ролей — в db_mcp/roles.py.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from db_mcp.roles import BusinessRole, DbPool
from db_mcp.settings import Settings

# Единый источник: бизнес-роль -> роль PostgreSQL (пул соединений).
# BUSINESS_ROLES выводится из BusinessRole, поэтому набор ролей и маппинг
# невозможно рассинхронизировать.
_BUSINESS_ROLE_TO_POOL: dict[BusinessRole, DbPool] = {
    BusinessRole.APPLICANT: DbPool.RO,
    BusinessRole.STUDENT: DbPool.RO,
    BusinessRole.TEACHER: DbPool.RO,
    BusinessRole.ADMIN: DbPool.ADMIN,
}


class UnknownRoleError(ValueError):
    """Неизвестная бизнес-роль."""


def _as_business_role(role: str | BusinessRole) -> BusinessRole:
    """Нормализовать роль в BusinessRole (строка или уже enum).

    Raises:
        UnknownRoleError: если строка не является известной бизнес-ролью.
    """
    if isinstance(role, BusinessRole):
        return role
    try:
        return BusinessRole(role)
    except ValueError:
        raise UnknownRoleError(f"Неизвестная роль: {role!r}") from None


class Pools:
    """Лениво создаваемые пулы соединений asyncpg по ролям PostgreSQL."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pools: dict[DbPool, asyncpg.Pool] = {}
        # Сериализует создание пула: два параллельных первых обращения не
        # должны создать два пула (второй утёк бы).
        self._lock = asyncio.Lock()

    @property
    def statement_timeout_ms(self) -> int:
        """Лимит исполнения одного запроса (мс), применяется в транзакции."""
        return self._settings.statement_timeout_ms

    async def _get(self, db_pool: DbPool) -> asyncpg.Pool:
        """Вернуть пул, создав его при первом обращении."""
        pool = self._pools.get(db_pool)
        if pool is None:
            async with self._lock:
                pool = self._pools.get(db_pool)
                if pool is None:
                    pool = await asyncpg.create_pool(
                        self._settings.dsn_for(db_pool), min_size=1, max_size=10
                    )
                    self._pools[db_pool] = pool
        return pool

    async def pool(self, db_pool: DbPool) -> asyncpg.Pool:
        """Пул соединений для заданной роли PostgreSQL."""
        return await self._get(db_pool)

    async def pool_for_role(self, role: str | BusinessRole) -> asyncpg.Pool:
        """Пул для бизнес-роли (выбор app_ro/app_admin)."""
        business_role = _as_business_role(role)
        return await self._get(_BUSINESS_ROLE_TO_POOL[business_role])

    async def audit(self) -> asyncpg.Pool:
        """Пул роли аудита app_audit (запись в query_log)."""
        return await self._get(DbPool.AUDIT)

    async def close(self) -> None:
        """Закрыть все пулы."""
        async with self._lock:
            for pool in self._pools.values():
                await pool.close()
            self._pools.clear()


async def resolve_internal_id(pools: Pools, user_id: str | int | None) -> str | None:
    """Резолвит номер учётки (`users.id`) в доменный `internal_id` (str).

    Выполняется через служебную роль `app_audit`, которая имеет право только на
    колонки (id, internal_id) таблицы users — без password_hash/email и прочего.

    Tolerant-поведение: пустой/нечисловой user_id, несуществующий users.id или
    NULL internal_id возвращают None (без ошибки). В connection_for это даёт
    app.user_id = NULL, что по RLS (deny-by-default) означает отсутствие строк
    — безопасно, без исключений.
    """
    if user_id is None or (isinstance(user_id, str) and not user_id.strip()):
        return None
    try:
        user_key = int(user_id)
    except (TypeError, ValueError):
        return None
    pool = await pools.audit()
    async with pool.acquire() as conn:
        internal_id = await conn.fetchval(
            "SELECT internal_id FROM users WHERE id = $1", user_key
        )
    return str(internal_id) if internal_id is not None else None


@asynccontextmanager
async def connection_for(
    pools: Pools, role: str | BusinessRole, user_id: str
) -> AsyncIterator[asyncpg.Connection]:
    """Соединение с установленным RLS-контекстом внутри транзакции.

    Контекст (app.role, app.user_id) задаётся в начале транзакции через
    set_config(..., is_local=true) — эквивалент SET LOCAL, действующий только
    на время её выполнения. Без контекста политики RLS (deny-by-default)
    не пропустят ни одной строки. Роль нормализуется в pool_for_role —
    неизвестная роль отклоняется до обращения к БД.

    `user_id` — это **номер учётки** (`users.id`, он же `sub` из JWT), а не
    доменный internal_id. Перед установкой контекста он резолвится в
    internal_id (student_id/staff_id) через `resolve_internal_id` и служебную
    роль `app_audit`. Для admin/applicant (internal_id может быть NULL) и для
    несуществующего users.id `app.user_id` не ставится вовсе — настройка
    отсутствует, `current_setting('app.user_id', true)` вернёт NULL, что по
    RLS (deny-by-default) означает отсутствие строк. Такой вариант выбран,
    потому что PostgreSQL хранит NULL в GUC как пустую строку "", а политика
    преподавателя кастует `current_setting('app.user_id')` в int.

    Также в транзакции задаётся `statement_timeout` (is_local=true): тяжёлый
    запрос не может держать соединение пула дольше заданного лимита.
    """
    business_role = _as_business_role(role)
    internal_id = await resolve_internal_id(pools, user_id)
    pool = await pools.pool_for_role(business_role)
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "SELECT set_config('app.role', $1, true)", business_role.value
        )
        # Если internal_id None, app.user_id НЕ ставим: PostgreSQL превращает
        # NULL в GUC в пустую строку "", а политика преподавателя кастует
        # current_setting('app.user_id') в int — это бы падало. Без установки
        # настройки current_setting(..., true) вернёт NULL -> RLS deny-by-default.
        if internal_id is not None:
            await conn.execute(
                "SELECT set_config('app.user_id', $1, true)", internal_id
            )
        await conn.execute(
            "SELECT set_config('statement_timeout', $1, true)",
            str(pools.statement_timeout_ms),
        )
        yield conn
