"""Тесты маршрутизации доступа по ролям (без реального подключения к БД)."""

from __future__ import annotations

import asyncio

import asyncpg
import pytest

from db_mcp.access import (
    Pools,
    UnknownRoleError,
    _as_business_role,
    connection_for,
)
from db_mcp.roles import BUSINESS_ROLES, BusinessRole, DbPool
from db_mcp.settings import Settings


def test_business_roles_defined() -> None:
    assert BUSINESS_ROLES == {"applicant", "student", "teacher", "admin"}


def test_business_role_values_match_enum() -> None:
    assert BUSINESS_ROLES == {role.value for role in BusinessRole}


def test_as_business_role_normalizes() -> None:
    assert _as_business_role("student") is BusinessRole.STUDENT
    assert _as_business_role(BusinessRole.ADMIN) is BusinessRole.ADMIN


def test_as_business_role_rejects_unknown() -> None:
    with pytest.raises(UnknownRoleError):
        _as_business_role("hacker")
    with pytest.raises(UnknownRoleError):
        _as_business_role("")


def test_pool_for_role_maps_all_business_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Каждая бизнес-роль отображается на ожидаемый пул PostgreSQL."""
    pools = Pools(Settings())
    resolved: list[DbPool] = []

    async def fake_get(_self: Pools, db_pool: DbPool) -> object:
        resolved.append(db_pool)
        return object()

    monkeypatch.setattr(Pools, "_get", fake_get)

    async def run() -> None:
        await pools.pool_for_role("applicant")
        await pools.pool_for_role(BusinessRole.STUDENT)
        await pools.pool_for_role("teacher")
        await pools.pool_for_role(BusinessRole.ADMIN)

    asyncio.run(run())
    assert resolved == [DbPool.RO, DbPool.RO, DbPool.RO, DbPool.ADMIN]


def test_unknown_role_rejected_before_connecting() -> None:
    pools = Pools(Settings())

    async def _connect(role: str | BusinessRole) -> None:
        async with connection_for(pools, role, "1"):
            pass  # pragma: no cover

    with pytest.raises(UnknownRoleError):
        asyncio.run(_connect("hacker"))
    with pytest.raises(UnknownRoleError):
        asyncio.run(_connect(""))


def test_statement_timeout_default() -> None:
    assert Settings().statement_timeout_ms == 10_000


def test_pool_created_once_under_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Два параллельных первых обращения создают ровно один пул."""
    pools = Pools(Settings())
    calls = 0

    async def fake_create_pool(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)  # widen the race window
        return object()

    monkeypatch.setattr(asyncpg, "create_pool", fake_create_pool)

    async def run() -> tuple[object, object]:
        first, second = await asyncio.gather(
            pools._get(DbPool.RO), pools._get(DbPool.RO)
        )
        return first, second

    first, second = asyncio.run(run())
    assert calls == 1
    assert first is second


class _FakeConn:
    """Фейк asyncpg-соединения: одновременно conn и контекст транзакции."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def transaction(self) -> _FakeConn:
        return self

    async def __aenter__(self) -> _FakeConn:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def execute(self, sql: str, *args: object) -> None:
        self.executed.append((sql, args))


class _FakePool:
    """Фейк пула: acquire() отдаёт фейк-соединение (как у asyncpg)."""

    def __init__(self) -> None:
        self.conn = _FakeConn()

    def acquire(self) -> _FakeConn:
        return self.conn


def test_connection_for_sets_rls_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Транзакция получает RLS-контекст и statement_timeout."""
    pools = Pools(Settings())
    fake_pool = _FakePool()

    async def fake_pool_for_role(_self: Pools, _role: object) -> _FakePool:
        return fake_pool

    monkeypatch.setattr(Pools, "pool_for_role", fake_pool_for_role)

    async def run() -> None:
        async with connection_for(pools, BusinessRole.STUDENT, "42"):
            pass

    asyncio.run(run())

    sqls = [sql for sql, _ in fake_pool.conn.executed]
    assert sqls == [
        "SELECT set_config('app.role', $1, true)",
        "SELECT set_config('app.user_id', $1, true)",
        "SELECT set_config('statement_timeout', $1, true)",
    ]
    role_args = fake_pool.conn.executed[0][1]
    timeout_args = fake_pool.conn.executed[2][1]
    assert role_args == ("student",)
    assert timeout_args == (str(Settings().statement_timeout_ms),)
