"""Тесты SchemaBuilder (без подключения к БД): формат описания и маскирование.

PK/FK приходят из статического TABLE_META, колонки — из мок-пула (как если
бы БД вернула information_schema.columns). Маскирование: гость (identity None)
не видит students/marks; аутентифицированный видит все доменные таблицы.
"""

from __future__ import annotations

import asyncio

import pytest

from db.models import Identity
from db.schema import SENSITIVE_COLUMNS, TABLE_META, SchemaBuilder


class _FakePool:
    """Фейк пула: fetch возвращает строки колонок каталога.

    Второй аргумент — массив исключаемых таблиц, как и в реальном _CATALOG_SQL:
    служебные таблицы не попадают в описание.
    """

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    async def fetch(self, _sql: str, *_args: object) -> list[dict[str, object]]:
        excluded = _args[0] if _args else ()
        return [
            dict(row)
            for row in self._rows
            if row["table_name"] not in excluded
        ]


class _FakePools:
    """Фейк Pools: ro() отдаёт пул с нужным набором колонок каталога."""

    def __init__(self, catalog: list[dict[str, object]]) -> None:
        self._catalog = catalog

    async def ro(self) -> _FakePool:
        return _FakePool(self._catalog)


def _column(table: str, column: str, nullable: bool = True) -> dict[str, object]:
    return {
        "table_name": table,
        "column_name": column,
        "data_type": "integer",
        "is_nullable": "YES" if nullable else "NO",
    }


# Полный каталог доменных таблиц (колоночных грантов в v2 нет — app_ro видит всё).
_FULL_CATALOG: list[dict[str, object]] = [
    _column("faculties", "id", nullable=False),
    _column("faculties", "title"),
    _column("faculties", "dean_id"),
    _column("students", "id", nullable=False),
    _column("students", "name"),
    _column("students", "surname"),
    _column("students", "patronymic"),
    _column("lesson_group", "lesson_id", nullable=False),
    _column("lesson_group", "group_id", nullable=False),
    _column("positions", "id", nullable=False),
    _column("positions", "title"),
    _column("users", "id"),
    _column("query_log", "id"),
]


def _describe(
    catalog: list[dict[str, object]], identity: Identity | None
) -> list[object]:
    builder = SchemaBuilder(_FakePools(catalog))
    return asyncio.run(builder.describe(identity))


def _table(tables: list[object], name: str) -> object:
    return next(t for t in tables if t.name == name)


_STUDENT_IDENTITY = Identity(user_id=1, student_id=7, staff_id=None)


def test_describe_includes_primary_key_and_foreign_keys() -> None:
    tables = _describe(_FULL_CATALOG, _STUDENT_IDENTITY)
    faculties = _table(tables, "faculties")
    assert faculties.primary_key == ["id"]
    assert [fk.model_dump() for fk in faculties.foreign_keys] == [
        {
            "column": "dean_id",
            "references_table": "staff",
            "references_column": "id",
        }
    ]


def test_describe_composite_primary_key() -> None:
    tables = _describe(_FULL_CATALOG, _STUDENT_IDENTITY)
    assert _table(tables, "lesson_group").primary_key == ["lesson_id", "group_id"]


def test_describe_empty_foreign_keys() -> None:
    tables = _describe(_FULL_CATALOG, _STUDENT_IDENTITY)
    assert _table(tables, "positions").foreign_keys == []


def test_pii_columns_are_not_pk_or_fk_targets() -> None:
    """Инвариант статики: PII-колонки не могут быть PK или целью FK."""
    pii_targets = {
        (ref["references_table"], ref["references_column"])
        for meta in TABLE_META.values()
        for ref in meta["foreign_keys"]  # type: ignore[typeddict-item]
    }
    for table, meta in TABLE_META.items():
        for column in SENSITIVE_COLUMNS.get(table, set()):
            assert column not in meta["primary_key"]  # type: ignore[operator]
            assert (table, column) not in pii_targets


def test_describe_guest_excludes_students_and_marks() -> None:
    tables = _describe(_FULL_CATALOG, None)
    names = {t.name for t in tables}
    assert names >= {"faculties", "positions"}
    assert "students" not in names
    assert "marks" not in names
    assert "users" not in names
    assert "query_log" not in names


def test_describe_authenticated_includes_all_domain_tables() -> None:
    tables = _describe(_FULL_CATALOG, _STUDENT_IDENTITY)
    names = {t.name for t in tables}
    assert {"faculties", "students", "positions", "lesson_group"} <= names
    assert "users" not in names
    assert "query_log" not in names


def test_describe_marks_sensitive_columns() -> None:
    tables = _describe(_FULL_CATALOG, _STUDENT_IDENTITY)
    student_cols = {c.name: c for c in _table(tables, "students").columns}
    assert student_cols["name"].sensitive is True
    assert student_cols["surname"].sensitive is True
    assert student_cols["id"].sensitive is False


def test_describe_nullable_flag() -> None:
    tables = _describe(_FULL_CATALOG, _STUDENT_IDENTITY)
    faculties_cols = {c.name: c for c in _table(tables, "faculties").columns}
    assert faculties_cols["id"].nullable is False
    assert faculties_cols["title"].nullable is True


def test_describe_excludes_service_tables() -> None:
    tables = _describe(_FULL_CATALOG, _STUDENT_IDENTITY)
    names = {t.name for t in tables}
    assert names >= {"faculties", "students"}
    assert "users" not in names
    assert "query_log" not in names


def test_describe_unknown_table_fallback() -> None:
    catalog = [_column("future_table", "id")]
    tables = _describe(catalog, _STUDENT_IDENTITY)
    assert len(tables) == 1
    future = tables[0]
    assert future.title is None
    assert future.description is None
    assert future.primary_key == []
    assert future.foreign_keys == []


def test_describe_columns_shape() -> None:
    tables = _describe(_FULL_CATALOG, _STUDENT_IDENTITY)
    cols = _table(tables, "faculties").columns[0]
    assert {"name", "type", "nullable", "description", "sensitive"} <= set(
        cols.model_dump()
    )


@pytest.mark.parametrize("meta", TABLE_META.values())
def test_table_meta_covers_v2_schema(meta: dict[str, object]) -> None:
    """Статическое описание таблиц v2: есть PK и поля описания."""
    assert meta["primary_key"]
    assert "columns" in meta
    assert "description" in meta