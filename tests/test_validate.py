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
        # set-операции
        "SELECT 1 UNION SELECT 2",
        "SELECT title FROM courses UNION SELECT title FROM groups",
        "SELECT 1 UNION ALL SELECT 2",
        "SELECT 1 INTERSECT SELECT 1",
        "SELECT 1 INTERSECT ALL SELECT 1",
        "SELECT 1 EXCEPT SELECT 2",
        "SELECT 1 EXCEPT ALL SELECT 2",
        "SELECT 1 UNION SELECT 2 UNION SELECT 3",
        "WITH x AS (SELECT 1) SELECT * FROM x UNION SELECT 2",
        "SELECT * FROM (SELECT 1 UNION SELECT 2) s",
        "SELECT 1 UNION SELECT 2 LIMIT 5",
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
        "SELECT * INTO t FROM a UNION SELECT * FROM b",
        "SELECT pg_sleep(10)",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT pg_catalog.pg_sleep(10)",  # схема-квалифицированное имя
        "SELECT nextval('query_log_id_seq')",
        "SELECT currval('query_log_id_seq')",
        "SELECT pg_advisory_lock(1)",
        "SELECT pg_advisory_unlock(1)",
        "SELECT pg_notify('chan', 'msg')",
        "SELECT 1 FOR UPDATE",
        "SELECT 1 FOR SHARE",
        "SELECT 1 UNION SELECT 2 FOR UPDATE",
        # DML, спрятанный в WITH (корень — SELECT, но это DML)
        "WITH del AS (DELETE FROM students RETURNING *) SELECT * FROM del",
        "WITH del AS (DELETE FROM students RETURNING *) SELECT * FROM del UNION SELECT * FROM del",
        "WITH ins AS (INSERT INTO students (name) VALUES ('x') RETURNING *) SELECT * FROM ins",
        "WITH upd AS (UPDATE students SET name = 'x' RETURNING *) SELECT * FROM upd",
        "SELECT 1 UNION SELECT 2; SELECT 3",  # мультистейтмент с set-операцией
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


def test_validate_applies_limit_to_union() -> None:
    result = validate("SELECT 1 UNION SELECT 2")
    assert result.limit_applied is True
    assert f"LIMIT {MAX_ROWS}" in result.sql


def test_validate_keeps_smaller_limit_on_union() -> None:
    result = validate("SELECT 1 UNION SELECT 2 LIMIT 5")
    assert result.limit_applied is False
    assert "LIMIT 5" in result.sql


def test_validate_clamps_too_large_limit_on_union() -> None:
    result = validate("SELECT 1 UNION SELECT 2 LIMIT 1000000")
    assert result.limit_applied is True
    assert f"LIMIT {MAX_ROWS}" in result.sql