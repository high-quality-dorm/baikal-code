"""Тесты доступа к БД: пулы, connection_for и RLS-контекст (без реальной БД)."""

from __future__ import annotations

import asyncio

import asyncpg
import pytest

from db import access as access_module
from db.access import Pools, connection_for
from db.models import Identity
from db.settings import Settings


def test_statement_timeout_default() -> None:
    assert Settings().statement_timeout_ms == 10_000


def test_pool_created_once_under_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
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
        return await asyncio.gather(pools.ro(), pools.ro())

    first, second = asyncio.run(run())
    assert calls == 1
    assert first is second


def test_ro_and_service_use_different_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пулы ro и service создаются по своим DSN."""
    created: list[tuple[str, ...]] = []

    async def fake_create_pool(dsn: str, *args: object, **kwargs: object) -> object:
        created.append((dsn,))
        return object()

    monkeypatch.setattr(asyncpg, "create_pool", fake_create_pool)

    async def run() -> None:
        pools = Pools(Settings())
        await pools.ro()
        await pools.service()

    asyncio.run(run())
    assert created == [
        (Settings().database_url_ro,),
        (Settings().database_url_service,),
    ]


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


def test_connection_for_sets_student_and_staff_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Аутентифицированный пользователь получает GUC student_id и staff_id."""
    pools = Pools(Settings())
    fake_pool = _FakePool()

    async def fake_ro(_self: Pools) -> _FakePool:
        return fake_pool

    monkeypatch.setattr(Pools, "ro", fake_ro)

    identity = Identity(user_id=3, student_id=7, staff_id=42)

    async def run() -> None:
        async with connection_for(pools, identity):
            pass

    asyncio.run(run())

    sqls = [sql for sql, _ in fake_pool.conn.executed]
    assert sqls == [
        "SELECT set_config('app.student_id', $1, true)",
        "SELECT set_config('app.staff_id', $1, true)",
        "SELECT set_config('statement_timeout', $1, true)",
    ]
    assert fake_pool.conn.executed[0][1] == ("7",)
    assert fake_pool.conn.executed[1][1] == ("42",)
    assert fake_pool.conn.executed[2][1] == (str(Settings().statement_timeout_ms),)


def test_connection_for_sets_only_present_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ставятся только заполненные GUC (например, только student_id)."""
    pools = Pools(Settings())
    fake_pool = _FakePool()

    async def fake_ro(_self: Pools) -> _FakePool:
        return fake_pool

    monkeypatch.setattr(Pools, "ro", fake_ro)

    identity = Identity(user_id=3, student_id=7, staff_id=None)

    async def run() -> None:
        async with connection_for(pools, identity):
            pass

    asyncio.run(run())

    sqls = [sql for sql, _ in fake_pool.conn.executed]
    assert sqls == [
        "SELECT set_config('app.student_id', $1, true)",
        "SELECT set_config('statement_timeout', $1, true)",
    ]
    assert not any("app.staff_id" in sql for sql, _ in fake_pool.conn.executed)


def test_connection_for_guest_sets_no_guc(monkeypatch: pytest.MonkeyPatch) -> None:
    """Гость (identity None) не получает ни одного GUC — только timeout.

    Без app.student_id/app.staff_id политики RLS (deny-by-default) не пропустят
    ни одной строки из students/marks, а общие таблицы открыты.
    """
    pools = Pools(Settings())
    fake_pool = _FakePool()

    async def fake_ro(_self: Pools) -> _FakePool:
        return fake_pool

    monkeypatch.setattr(Pools, "ro", fake_ro)

    async def run() -> None:
        async with connection_for(pools, None):
            pass

    asyncio.run(run())

    sqls = [sql for sql, _ in fake_pool.conn.executed]
    assert sqls == [
        "SELECT set_config('statement_timeout', $1, true)",
    ]
    assert not any("app." in sql for sql, _ in fake_pool.conn.executed)