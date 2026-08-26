"""Тесты резолюции identity (без подключения к БД).

Проверяется контракт SQL через служебную роль app_service, tolerant-поведение
(гость, неактивная учётка) и вывод роли для app-уровня.
"""

from __future__ import annotations

import asyncio

import pytest

from db.access import Pools
from db.identity import resolve_identity, resolve_role
from db.models import Identity
from db.settings import Settings


class _FakeConn:
    """Фейк asyncpg-соединения: накапливает запросы, отдаёт fetchrow.

    asyncpg.Record поддерживает доступ по имени колонки (`row["id"]`), поэтому
    фейк возвращает dict с теми же ключами.
    """

    def __init__(self, result: object) -> None:
        self._result = result
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    async def fetchrow(self, sql: str, *args: object) -> object:
        self.executed.append((sql, args))
        return self._result

    async def __aenter__(self) -> "_FakeConn":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakePool:
    """Фейк пула: acquire() отдаёт фейк-соединение."""

    def __init__(self, conn: _FakeConn) -> None:
        self.conn = conn

    def acquire(self) -> _FakeConn:
        return self.conn


def _make_pools(monkeypatch: pytest.MonkeyPatch, conn: _FakeConn) -> Pools:
    pools = Pools(Settings())
    pool = _FakePool(conn)

    async def fake_service(_self: Pools) -> _FakePool:
        return pool

    monkeypatch.setattr(Pools, "service", fake_service)
    return pools


# строка из SELECT id, student_id, staff_id, is_active
_IDENTITY_ROW = {"id": 3, "student_id": 7, "staff_id": None, "is_active": True}


def test_resolve_identity_found(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn(_IDENTITY_ROW)
    pools = _make_pools(monkeypatch, conn)

    identity = asyncio.run(resolve_identity(pools, 3))

    assert identity == Identity(user_id=3, student_id=7, staff_id=None, is_active=True)
    assert conn.executed[0][1] == (3,)


def test_resolve_identity_staff(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn({"id": 4, "student_id": None, "staff_id": 9, "is_active": True})
    pools = _make_pools(monkeypatch, conn)

    identity = asyncio.run(resolve_identity(pools, 4))

    assert identity == Identity(user_id=4, student_id=None, staff_id=9, is_active=True)


def test_resolve_identity_none_for_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Несуществующий user_id -> None (гость), без ошибки."""
    conn = _FakeConn(None)
    pools = _make_pools(monkeypatch, conn)

    assert asyncio.run(resolve_identity(pools, 999)) is None


def test_resolve_identity_none_for_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Неактивная учётка -> None (доступ как гость)."""
    conn = _FakeConn({"id": 5, "student_id": 1, "staff_id": None, "is_active": False})
    pools = _make_pools(monkeypatch, conn)

    assert asyncio.run(resolve_identity(pools, 5)) is None


def test_resolve_identity_none_for_guest(monkeypatch: pytest.MonkeyPatch) -> None:
    """user_id=None (гость) -> None без обращения к БД."""
    conn = _FakeConn(_IDENTITY_ROW)
    pools = _make_pools(monkeypatch, conn)

    assert asyncio.run(resolve_identity(pools, None)) is None
    assert conn.executed == []


def test_resolve_role_student(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn({"student_id": 7, "is_active": True, "position": None})
    pools = _make_pools(monkeypatch, conn)

    assert asyncio.run(resolve_role(pools, 1)) == "student"


def test_resolve_role_position(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn({"student_id": None, "is_active": True, "position": "dean"})
    pools = _make_pools(monkeypatch, conn)

    assert asyncio.run(resolve_role(pools, 2)) == "dean"


@pytest.mark.parametrize("position", ["teacher", "head", "admin"])
def test_resolve_role_known_positions(
    monkeypatch: pytest.MonkeyPatch, position: str
) -> None:
    conn = _FakeConn({"student_id": None, "is_active": True, "position": position})
    pools = _make_pools(monkeypatch, conn)

    assert asyncio.run(resolve_role(pools, 2)) == position


def test_resolve_role_unknown_position(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn({"student_id": None, "is_active": True, "position": "janitor"})
    pools = _make_pools(monkeypatch, conn)

    assert asyncio.run(resolve_role(pools, 2)) is None


def test_resolve_role_none_for_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn({"student_id": None, "is_active": False, "position": "dean"})
    pools = _make_pools(monkeypatch, conn)

    assert asyncio.run(resolve_role(pools, 2)) is None


def test_resolve_role_none_for_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn(None)
    pools = _make_pools(monkeypatch, conn)

    assert asyncio.run(resolve_role(pools, 999)) is None