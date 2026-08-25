"""Тесты сериализации ответа execute_query (без подключения к БД)."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from db_mcp.server import Gateway, _jsonable, _serialize_records
from db_mcp.settings import Settings


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


def test_execute_query_returns_columns_rows_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """execute_query отдаёт columns/rows с сохранением дублей колонок."""
    import db_mcp.server as server_module

    gateway = Gateway(Settings())
    gateway._auditor.record = _noop_record  # type: ignore[method-assign]

    records = [_FakeRecord(["student_id", "course_id"], [7, 101])]

    @asynccontextmanager
    async def fake_connection_for(_pools: object, _role: object, _user_id: object):
        yield _FakeConn(records)

    monkeypatch.setattr(server_module, "connection_for", fake_connection_for)

    out = asyncio.run(gateway.execute_query("SELECT 1", "admin", "1"))
    payload = json.loads(out)
    assert payload["columns"] == ["student_id", "course_id"]
    assert payload["rows"] == [[7, 101]]
    assert payload["row_count"] == 1
