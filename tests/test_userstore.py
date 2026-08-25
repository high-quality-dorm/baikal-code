"""Тесты хранилища учёток db_mcp (UserStore) — без реальной БД.

Проверяется контракт SQL (фиксированные параметризованные запросы),
валидация роли/internal_id и обработка ошибок (дубликат логина, not-found).
"""

from __future__ import annotations

import pytest

from db_mcp.access import Pools
from db_mcp.settings import Settings
from db_mcp.userstore import (
    DuplicateLoginError,
    InvalidRoleError,
    UserStore,
    UserStoreError,
    _validate_internal_id,
    _validate_role,
)


class _FakeConn:
    """Фейк asyncpg-соединения: накапливает выполненные запросы."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.fetchrow_result: object = None
        self.fetch_result: list[object] = []
        self.fetchval_result: object = None
        self.execute_exc: Exception | None = None

    async def fetchrow(self, sql: str, *args: object) -> object:
        self.executed.append((sql, args))
        return self.fetchrow_result

    async def fetch(self, sql: str, *args: object) -> list[object]:
        self.executed.append((sql, args))
        return self.fetch_result

    async def fetchval(self, sql: str, *args: object) -> object:
        self.executed.append((sql, args))
        if self.execute_exc:
            raise self.execute_exc
        return self.fetchval_result

    async def execute(self, sql: str, *args: object) -> None:
        self.executed.append((sql, args))
        if self.execute_exc:
            raise self.execute_exc

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


def _make_store(monkeypatch: pytest.MonkeyPatch, conn: _FakeConn) -> UserStore:
    """Собирает UserStore с подменённым служебным пулом."""
    pools = Pools(Settings())
    pool = _FakePool(conn)

    async def fake_service(_self: Pools) -> _FakePool:
        return pool

    monkeypatch.setattr(Pools, "service", fake_service)
    return UserStore(pools)


_ROW = (7, "ext-7", "a@b.c", "hash", "student", 100, "Студент", True)


def test_validate_role_accepts_business_roles() -> None:
    assert _validate_role("student") == "student"
    assert _validate_role("admin") == "admin"


def test_validate_role_rejects_unknown() -> None:
    with pytest.raises(InvalidRoleError):
        _validate_role("hacker")


def test_validate_internal_id() -> None:
    assert _validate_internal_id(None) is None
    assert _validate_internal_id(5) == 5
    with pytest.raises(UserStoreError):
        _validate_internal_id(0)


@pytest.mark.anyio
async def test_get_credentials_found(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn()
    conn.fetchrow_result = _ROW
    store = _make_store(monkeypatch, conn)

    user = await store.get_credentials("a@b.c")

    assert user is not None
    assert user.id == 7
    assert user.email == "a@b.c"
    assert user.role == "student"
    assert user.internal_id == 100
    assert user.is_active is True
    sql = conn.executed[0][0]
    assert "FROM users" in sql and "email = $1 OR external_id = $1" in sql


@pytest.mark.anyio
async def test_get_credentials_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn()
    conn.fetchrow_result = None
    store = _make_store(monkeypatch, conn)

    assert await store.get_credentials("nobody") is None


@pytest.mark.anyio
async def test_find(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn()
    conn.fetchrow_result = _ROW
    store = _make_store(monkeypatch, conn)

    user = await store.find(7)

    assert user is not None and user.id == 7
    assert conn.executed[0][1] == (7,)


@pytest.mark.anyio
async def test_all(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn()
    conn.fetch_result = [_ROW, (8, "ext-8", None, "h", "teacher", None, None, True)]
    store = _make_store(monkeypatch, conn)

    users = await store.all()

    assert len(users) == 2
    assert users[0].id == 7
    assert users[1].role == "teacher"
    assert users[1].email is None


@pytest.mark.anyio
async def test_create_assigns_id_and_uses_fixed_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn()
    conn.fetchval_result = 10
    store = _make_store(monkeypatch, conn)

    user = await store.create(
        external_id="ext-10",
        email="x@y.z",
        password_hash="hash",
        role="student",
        internal_id=42,
        display_name="Иван",
    )

    assert user.id == 10
    sql, args = conn.executed[0]
    assert sql.strip().startswith("INSERT INTO users")
    assert args == ("ext-10", "x@y.z", "hash", "student", 42, "Иван", True)


@pytest.mark.anyio
async def test_create_rejects_bad_role(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn()
    store = _make_store(monkeypatch, conn)

    with pytest.raises(InvalidRoleError):
        await store.create(
            external_id="x",
            email="a@b.c",
            password_hash="h",
            role="hacker",
            internal_id=None,
            display_name=None,
        )
    assert conn.executed == []


def _unique_violation() -> Exception:
    exc = Exception("duplicate key value violates unique constraint")
    setattr(exc, "sqlstate", "23505")
    return exc


@pytest.mark.anyio
async def test_create_duplicate_login_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn()
    conn.fetchval_result = None
    conn.execute_exc = _unique_violation()
    store = _make_store(monkeypatch, conn)

    with pytest.raises(DuplicateLoginError):
        await store.create(
            external_id="ext-10",
            email="x@y.z",
            password_hash="hash",
            role="student",
            internal_id=None,
            display_name=None,
        )


@pytest.mark.anyio
async def test_update_preserves_existing_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn()
    conn.fetchrow_result = _ROW
    store = _make_store(monkeypatch, conn)

    updated = await store.update(
        7,
        email=None,
        password_hash="newhash",
        role=None,
        internal_id=None,
        display_name=None,
        is_active=True,
    )

    assert updated is not None
    assert updated.id == 7
    assert updated.password_hash == "newhash"
    assert updated.email == "a@b.c"  # непустые поля сохраняются
    assert updated.role == "student"
    sql, args = conn.executed[-1]
    assert sql.strip().startswith("UPDATE users")
    assert args[0] == "a@b.c"  # email из текущей учётки
    assert args[1] == "newhash"
    assert args[6] == 7


@pytest.mark.anyio
async def test_update_missing_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn()
    conn.fetchrow_result = None
    store = _make_store(monkeypatch, conn)

    updated = await store.update(
        999,
        email=None,
        password_hash=None,
        role=None,
        internal_id=None,
        display_name=None,
        is_active=None,
    )

    assert updated is None


@pytest.mark.anyio
async def test_deactivate(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn()
    conn.fetchrow_result = _ROW
    store = _make_store(monkeypatch, conn)

    ok = await store.deactivate(7)

    assert ok is True
    sql, args = conn.executed[-1]
    assert "is_active = FALSE" in sql
    assert args == (7,)


@pytest.mark.anyio
async def test_deactivate_missing_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn()
    conn.fetchrow_result = None
    store = _make_store(monkeypatch, conn)

    assert await store.deactivate(999) is False
    assert not any("is_active = FALSE" in sql for sql, _ in conn.executed)