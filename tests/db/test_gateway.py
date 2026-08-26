"""Тесты сериализации ответа execute_query (без подключения к БД)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from db import gateway as gateway_module
from db.gateway import Gateway, _jsonable, _serialize_records
from db.models import Identity
from db.settings import Settings


class _FakeRecord:
    """Фейк asyncpg.Record: ключи и значения по позициям."""

    def __init__(self, keys: list[str], values: list[object]) -> None:
        self._keys = keys
        self._values = values

    def keys(self) -> tuple[str, ...]:
        return tuple(self._keys)

    def __iter__(self):
        return iter(self._values)


def test_jsonable_primitive_passthrough() -> None:
    assert _jsonable(None) is None
    assert _jsonable(True) is True
    assert _jsonable(42) == 42
    assert _jsonable(3.14) == 3.14
    assert _jsonable("текст") == "текст"


def test_jsonable_decimal_is_lossless() -> None:
    value = Decimal("12345678901234567890.123456789")
    assert _jsonable(value) == "12345678901234567890.123456789"


def test_jsonable_datetime_uuid() -> None:
    assert _jsonable(datetime(2026, 9, 15, 10, 30)) == "2026-09-15T10:30:00"
    assert _jsonable(date(2026, 9, 15)) == "2026-09-15"
    assert _jsonable(UUID("12345678-1234-5678-1234-567812345678")) == (
        "12345678-1234-5678-1234-567812345678"
    )


def test_serialize_records_preserves_duplicate_columns() -> None:
    records = [
        _FakeRecord(["id", "id", "title"], [1, "a", "Лекции"]),
        _FakeRecord(["id", "id", "title"], [2, "b", "Практика"]),
    ]
    columns, rows = _serialize_records(records)
    assert columns == ["id", "id", "title"]
    assert rows == [[1, "a", "Лекции"], [2, "b", "Практика"]]


def test_serialize_records_empty() -> None:
    assert _serialize_records([]) == ([], [])


def test_serialize_records_jsonable_values() -> None:
    records = [_FakeRecord(["amount", "ts"], [Decimal("1.5"), date(2026, 1, 1)])]
    _, rows = _serialize_records(records)
    assert rows == [["1.5", "2026-01-01"]]


class _FakeConn:
    def __init__(self, records: list[object]) -> None:
        self._records = records

    async def fetch(self, _sql: str) -> list[object]:
        return self._records


async def _noop_record(**_: object) -> None:
    return None


def test_execute_query_audits_user_id_as_users_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Аудит пишет номер учётки (users.id), а не резолвленный id.

    В query_log.user_id должен попадать переданный users.id как есть; для
    гостя (user_id None) — None.
    """
    gateway = Gateway(Settings())
    recorded: dict[str, object] = {}

    async def fake_record(**kwargs: object) -> None:
        recorded.update(kwargs)

    gateway._auditor.record = fake_record  # type: ignore[method-assign]

    @asynccontextmanager
    async def fake_connection_for(_pools: object, identity: object):
        yield _FakeConn([_FakeRecord(["student_id"], [7])])

    monkeypatch.setattr(gateway_module, "connection_for", fake_connection_for)

    asyncio.run(gateway.execute_query("SELECT 1", 3))
    assert recorded["user_id"] == "3"
    assert recorded["status"] == "ok"
    assert recorded["role"] is None


def test_execute_query_guest_audits_no_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Гость (user_id None) аудируется с user_id None."""
    gateway = Gateway(Settings())
    recorded: dict[str, object] = {}

    async def fake_record(**kwargs: object) -> None:
        recorded.update(kwargs)

    gateway._auditor.record = fake_record  # type: ignore[method-assign]

    @asynccontextmanager
    async def fake_connection_for(_pools: object, identity: object):
        assert identity is None
        yield _FakeConn([_FakeRecord(["title"], ["Факультет"])])

    monkeypatch.setattr(gateway_module, "connection_for", fake_connection_for)

    asyncio.run(gateway.execute_query("SELECT 1", None))
    assert recorded["user_id"] is None
    assert recorded["status"] == "ok"


def test_execute_query_returns_columns_rows_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """execute_query отдаёт QueryResult с columns/rows и дублями колонок."""
    gateway = Gateway(Settings())
    gateway._auditor.record = _noop_record  # type: ignore[method-assign]

    records = [_FakeRecord(["student_id", "course_id"], [7, 101])]

    @asynccontextmanager
    async def fake_connection_for(_pools: object, identity: object):
        yield _FakeConn(records)

    monkeypatch.setattr(gateway_module, "connection_for", fake_connection_for)

    out = asyncio.run(gateway.execute_query("SELECT 1", 1))
    assert out.columns == ["student_id", "course_id"]
    assert out.rows == [[7, 101]]
    assert out.row_count == 1
    assert out.truncated is False


def test_execute_query_passes_resolved_identity_to_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """connection_for получает identity, резолвленный из user_id."""
    gateway = Gateway(Settings())
    gateway._auditor.record = _noop_record  # type: ignore[method-assign]

    captured: list[object] = []

    @asynccontextmanager
    async def fake_connection_for(_pools: object, identity: object):
        captured.append(identity)
        yield _FakeConn([])

    monkeypatch.setattr(gateway_module, "connection_for", fake_connection_for)

    async def fake_resolve_identity(_pools: object, user_id: object) -> Identity:
        return Identity(user_id=user_id, student_id=7, staff_id=None)

    monkeypatch.setattr(
        gateway_module,
        "resolve_identity",
        fake_resolve_identity,
    )

    asyncio.run(gateway.execute_query("SELECT 1", 3))
    assert captured == [Identity(user_id=3, student_id=7, staff_id=None)]