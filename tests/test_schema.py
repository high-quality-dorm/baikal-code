"""Тесты SchemaBuilder (без подключения к БД): формат описания и маскирование.

PK/FK приходят из статического TABLE_META, колонки — из мок-пула (как если
бы БД вернула information_schema.columns под роль).
"""

from __future__ import annotations

import asyncio

import pytest

from db_mcp.schema import SENSITIVE_COLUMNS, TABLE_META, SchemaBuilder


class _FakePool:
    """Фейк пула: fetch возвращает строки колонок каталога.

    Второй аргумент — массив исключаемых таблиц (`EXCLUDED_TABLES`), как и в
    реальном _CATALOG_SQL: служебные таблицы не попадают в описание.
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
    """Фейк Pools: роль -> пул с нужным набором колонок каталога."""

    def __init__(self, rows_by_role: dict[str, list[dict[str, object]]]) -> None:
        self._rows_by_role = rows_by_role

    async def pool_for_role(self, role: object) -> _FakePool:
        key = role.value if isinstance(role, object) and hasattr(role, "value") else str(role)
        return _FakePool(self._rows_by_role.get(key, self._rows_by_role.get(str(role), [])))


def _column(table: str, column: str, nullable: bool = True) -> dict[str, object]:
    return {
        "table_name": table,
        "column_name": column,
        "data_type": "integer",
        "is_nullable": "YES" if nullable else "NO",
    }


# Полный каталог (как видит app_admin): все таблицы со всеми колонками.
_FULL_CATALOG: list[dict[str, object]] = [
    _column("faculties", "faculty_id", nullable=False),
    _column("faculties", "title"),
    _column("students", "student_id", nullable=False),
    _column("students", "name"),
    _column("students", "passport"),
    _column("course_instructors", "course_id", nullable=False),
    _column("course_instructors", "staff_id", nullable=False),
    _column("roles", "id", nullable=False),
    _column("roles", "title"),
    _column("users", "id"),
    _column("query_log", "id"),
]

# Каталог под app_ro: PII-колонки студентов отсутствуют (как в БД),
# служебные таблицы не видны вовсе.
_RO_CATALOG: list[dict[str, object]] = [
    row
    for row in _FULL_CATALOG
    if not (row["table_name"] == "students" and row["column_name"] in {"name", "passport"})
    and row["table_name"] not in {"users", "query_log"}
]


def _describe(catalog: list[dict[str, object]], role: str) -> list[dict[str, object]]:
    builder = SchemaBuilder(_FakePools({role: catalog}))
    return asyncio.run(builder.describe(role))


def _table(tables: list[dict[str, object]], name: str) -> dict[str, object]:
    return next(t for t in tables if t["name"] == name)


def test_describe_includes_primary_key_and_foreign_keys() -> None:
    tables = _describe(_FULL_CATALOG, "admin")
    faculties = _table(tables, "faculties")
    assert faculties["primary_key"] == ["faculty_id"]
    assert faculties["foreign_keys"] == [
        {"column": "dean_id", "references_table": "staff", "references_column": "staff_id"}
    ]


def test_describe_composite_primary_key() -> None:
    tables = _describe(_FULL_CATALOG, "admin")
    assert _table(tables, "course_instructors")["primary_key"] == ["course_id", "staff_id"]


def test_describe_empty_foreign_keys() -> None:
    tables = _describe(_FULL_CATALOG, "admin")
    assert _table(tables, "roles")["foreign_keys"] == []


def test_pii_columns_are_not_pk_or_fk_targets() -> None:
    """Инвариант статики: PII-колонки не могут быть PK или целью FK."""
    pii_targets = {
        (ref["references_table"], ref["references_column"])
        for meta in TABLE_META.values()
        for ref in meta["foreign_keys"]
    }
    for table, meta in TABLE_META.items():
        for column in SENSITIVE_COLUMNS.get(table, set()):
            assert column not in meta["primary_key"]
            assert (table, column) not in pii_targets


def test_describe_masks_pii_by_role() -> None:
    student_tables = _describe(_RO_CATALOG, "student")
    admin_tables = _describe(_FULL_CATALOG, "admin")

    student_cols = {c["name"] for c in _table(student_tables, "students")["columns"]}
    assert {"name", "passport"} & student_cols == set()

    admin_cols = _table(admin_tables, "students")["columns"]
    assert {"name", "passport"} <= {c["name"] for c in admin_cols}


def test_describe_marks_sensitive_columns() -> None:
    tables = _describe(_FULL_CATALOG, "admin")
    student_cols = {c["name"]: c for c in _table(tables, "students")["columns"]}
    assert student_cols["name"]["sensitive"] is True
    assert student_cols["student_id"]["sensitive"] is False


def test_describe_nullable_flag() -> None:
    tables = _describe(_FULL_CATALOG, "admin")
    faculties_cols = {c["name"]: c for c in _table(tables, "faculties")["columns"]}
    assert faculties_cols["faculty_id"]["nullable"] is False
    assert faculties_cols["title"]["nullable"] is True


def test_describe_excludes_service_tables() -> None:
    tables = _describe(_FULL_CATALOG, "admin")
    assert {t["name"] for t in tables} >= {"faculties", "students"}
    assert "users" not in {t["name"] for t in tables}
    assert "query_log" not in {t["name"] for t in tables}


def test_describe_unknown_table_fallback() -> None:
    catalog = [_column("future_table", "id")]
    tables = _describe(catalog, "admin")
    assert len(tables) == 1
    future = tables[0]
    assert future["title"] is None
    assert future["description"] is None
    assert future["primary_key"] == []
    assert future["foreign_keys"] == []


def test_describe_columns_shape() -> None:
    tables = _describe(_FULL_CATALOG, "admin")
    cols = _table(tables, "faculties")["columns"][0]
    assert {"name", "type", "nullable", "description", "sensitive"} <= cols.keys()
