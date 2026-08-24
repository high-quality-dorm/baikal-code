"""Тесты валидации SQL (чистая логика, без подключения к БД)."""

from __future__ import annotations

import pytest

from db_mcp.validate import MAX_ROWS, ValidationError, validate


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM students",
        "select faculty_id, title from faculties",
        "SELECT count(*) FROM academic_records",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "SELECT * FROM groups WHERE admission_year = 2025",
        'SELECT title FROM courses WHERE title LIKE \'%ы%\';',  # trailing semicolon
        "SELECT 1",  # -- комментарий в конце
    ],
)
def test_validate_accepts_read_only_select(sql: str) -> None:
    result = validate(sql)
    assert result.sql
    assert result.sql.upper().startswith("SELECT") or result.sql.upper().startswith("WITH")


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   ",
        ";",
        "DELETE FROM students",
        "INSERT INTO students (name) VALUES ('x')",
        "UPDATE students SET name = 'x'",
        "TRUNCATE TABLE students",
        "DROP TABLE students",
        "CREATE TABLE t (id int)",
        "COPY students FROM '/tmp/f'",
        "SELECT 1; SELECT 2",  # мультистейтмент
        "SELECT * INTO t FROM students",
        "SELECT pg_sleep(10)",
        "SELECT pg_read_file('/etc/passwd')",
        "SET LOCAL app.role = 'admin'",
        "SHOW ALL",
    ],
)
def test_validate_rejects_unsafe_sql(sql: str) -> None:
    with pytest.raises(ValidationError):
        validate(sql)


def test_validate_applies_limit_when_missing() -> None:
    result = validate("SELECT * FROM students")
    assert result.limit_applied is True
    assert f"LIMIT {MAX_ROWS}" in result.sql


def test_validate_clamps_too_large_limit() -> None:
    result = validate(f"SELECT * FROM students LIMIT {MAX_ROWS + 1000}")
    assert result.limit_applied is True
    assert f"LIMIT {MAX_ROWS}" in result.sql


def test_validate_keeps_smaller_limit() -> None:
    result = validate("SELECT * FROM students LIMIT 5")
    assert result.limit_applied is False
    assert "LIMIT 5" in result.sql