"""Тесты маршрутизации доступа по ролям (без реального подключения к БД)."""

from __future__ import annotations

import asyncio

import asyncpg
import pytest

from db_mcp import access as access_module
from db_mcp.access import (
    Pools,
    UnknownRoleError,
    _as_business_role,
    connection_for,
    resolve_internal_id,
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


class _FakeValConn:
    """Фейк соединения с fetchval (для тестов резолвера)."""

    def __init__(self, result: object) -> None:
        self._result = result
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    async def fetchval(self, sql: str, *args: object) -> object:
        self.executed.append((sql, args))
        return self._result

    async def __aenter__(self) -> "_FakeValConn":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeAuditPool:
    """Фейк пула аудита: acquire() отдаёт фейк-соединение с fetchval."""

    def __init__(self, conn: _FakeValConn) -> None:
        self.conn = conn

    def acquire(self) -> _FakeValConn:
        return self.conn


def test_resolve_internal_id_found(monkeypatch: pytest.MonkeyPatch) -> None:
    pools = Pools(Settings())
    fake_conn = _FakeValConn(7)
    fake_pool = _FakeAuditPool(fake_conn)

    async def fake_audit(_self: Pools) -> _FakeAuditPool:
        return fake_pool

    monkeypatch.setattr(Pools, "audit", fake_audit)

    async def run() -> str | None:
        return await resolve_internal_id(pools, "3")

    assert asyncio.run(run()) == "7"
    assert fake_conn.executed[0][0].startswith("SELECT internal_id FROM users")


def test_resolve_internal_id_null_internal_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """users.id существует, но internal_id = NULL -> None (без ошибки)."""
    pools = Pools(Settings())
    fake_conn = _FakeValConn(None)
    fake_pool = _FakeAuditPool(fake_conn)

    async def fake_audit(_self: Pools) -> _FakeAuditPool:
        return fake_pool

    monkeypatch.setattr(Pools, "audit", fake_audit)

    async def run() -> str | None:
        return await resolve_internal_id(pools, "1")

    assert asyncio.run(run()) is None


@pytest.mark.parametrize("unknown", ["999999", "-5"])
def test_resolve_internal_id_unknown_numeric_id_goes_to_db(
    monkeypatch: pytest.MonkeyPatch, unknown: str
) -> None:
    """Числовой, но несуществующий users.id -> обращение к БД и None."""
    pools = Pools(Settings())
    fake_conn = _FakeValConn(None)
    fake_pool = _FakeAuditPool(fake_conn)

    async def fake_audit(_self: Pools) -> _FakeAuditPool:
        return fake_pool

    monkeypatch.setattr(Pools, "audit", fake_audit)

    async def run() -> str | None:
        return await resolve_internal_id(pools, unknown)

    assert asyncio.run(run()) is None
    assert fake_conn.executed[0][1] == (int(unknown),)


@pytest.mark.parametrize("bad", [None, "", "  ", "abc", "3.14"])
def test_resolve_internal_id_tolerant_bad_input(
    monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    """Пустой/нечисловой user_id -> None без обращения к БД и без ошибки."""
    pools = Pools(Settings())
    called = False

    async def fake_audit(_self: Pools) -> _FakeAuditPool:
        nonlocal called
        called = True
        return _FakeAuditPool(_FakeValConn(None))

    monkeypatch.setattr(Pools, "audit", fake_audit)

    async def run() -> str | None:
        return await resolve_internal_id(pools, bad)  # type: ignore[arg-type]

    assert asyncio.run(run()) is None
    assert not called


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

    async def fake_resolve(_self: Pools, _user_id: object) -> str:
        return "42"

    monkeypatch.setattr(Pools, "pool_for_role", fake_pool_for_role)
    monkeypatch.setattr(access_module, "resolve_internal_id", fake_resolve)

    async def run() -> None:
        async with connection_for(pools, BusinessRole.STUDENT, "3"):
            pass

    asyncio.run(run())

    sqls = [sql for sql, _ in fake_pool.conn.executed]
    assert sqls == [
        "SELECT set_config('app.role', $1, true)",
        "SELECT set_config('app.user_id', $1, true)",
        "SELECT set_config('statement_timeout', $1, true)",
    ]
    role_args = fake_pool.conn.executed[0][1]
    user_args = fake_pool.conn.executed[1][1]
    timeout_args = fake_pool.conn.executed[2][1]
    assert role_args == ("student",)
    assert user_args == ("42",)  # резолвленный internal_id, а не users.id "3"
    assert timeout_args == (str(Settings().statement_timeout_ms),)


def test_connection_for_null_internal_id_skips_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NULL internal_id (admin/applicant/несуществующий) -> app.user_id не ставится.

    PostgreSQL хранит NULL в GUC как пустую строку, которая ломала бы политику
    преподавателя (`current_setting(...)::int`). Поэтому настройка просто
    отсутствует -> current_setting(..., true) даёт NULL -> RLS deny-by-default.
    """
    pools = Pools(Settings())
    fake_pool = _FakePool()

    async def fake_pool_for_role(_self: Pools, _role: object) -> _FakePool:
        return fake_pool

    async def fake_resolve(_self: Pools, _user_id: object) -> None:
        return None

    monkeypatch.setattr(Pools, "pool_for_role", fake_pool_for_role)
    monkeypatch.setattr(access_module, "resolve_internal_id", fake_resolve)

    async def run() -> None:
        async with connection_for(pools, BusinessRole.ADMIN, "1"):
            pass

    asyncio.run(run())

    sqls = [sql for sql, _ in fake_pool.conn.executed]
    assert sqls == [
        "SELECT set_config('app.role', $1, true)",
        "SELECT set_config('statement_timeout', $1, true)",
    ]
    assert not any("app.user_id" in sql for sql, _ in fake_pool.conn.executed)
