"""Инварианты публичных агрегатных вью (`db/04_views.sql`) и FORCE RLS.

Публичные агрегаты по студентам — единственный способ для app_ro (гостя и
авторизованных) узнать численность студентов без персональных данных. Эти
тесты защищают механизм:

- в `03_rls.sql` FORCE снят **только** с `students` (владелец должен обходить
  RLS, чтобы считать вью), на `marks` FORCE остаётся;
- в `04_views.sql` вью — только агрегаты `count(...)` без PII-колонок, ссылаются
  только на разрешённые базовые таблицы, а гранты выданы поимённо (не
  `ON ALL TABLES` — это вернуло бы app_ro доступ к `users`/`query_log`).
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_RLS = (_REPO_ROOT / "db" / "03_rls.sql").read_text(encoding="utf-8")
_VIEWS = (_REPO_ROOT / "db" / "04_views.sql").read_text(encoding="utf-8")

# Ожидаемый набор публичных вью
VIEW_NAMES = frozenset(
    {
        "v_students_total",
        "v_students_by_faculty",
        "v_students_by_specialization",
        "v_students_by_group",
        "v_students_by_status",
        "v_students_by_admission_year",
        "v_students_expelled",
    }
)

# Базовые таблицы, которые вью могут использовать
ALLOWED_TABLES = frozenset(
    {"students", "groups", "specializations", "faculties", "student_statuses"}
)

# PII-колонки студентов: не должны появляться в 04_views.sql вовсе
_PII_RE = re.compile(r"\b(name|surname|patronymic)\b", re.IGNORECASE)
_FROM_JOIN_RE = re.compile(r"\b(?:FROM|JOIN)\s+([a-z_]+)", re.IGNORECASE)
_CREATE_VIEW_RE = re.compile(r"CREATE VIEW\s+([a-z_]+)", re.IGNORECASE)
_GRANT_RE = re.compile(r"GRANT\s+SELECT\s+ON\s+([a-z_]+)", re.IGNORECASE)


def _students_block() -> str:
    """Блок политик таблицы students (между маркерами таблиц)."""
    return _RLS.split("-- ===== students =====")[1].split("-- ===== marks =====")[0]


def _view_block(name: str) -> str:
    """Определение вью до следующего CREATE VIEW."""
    block = _VIEWS.split(f"CREATE VIEW {name} AS")[1]
    return block.split("CREATE VIEW")[0]


def test_force_removed_from_students_kept_on_marks() -> None:
    """FORCE снят с students (владелец обходит RLS для вью), на marks остаётся."""
    assert "FORCE ROW LEVEL SECURITY" not in _students_block()
    marks_block = _RLS.split("-- ===== marks =====")[1]
    assert "FORCE ROW LEVEL SECURITY" in marks_block


def test_students_rls_still_enabled() -> None:
    """RLS на students остаётся включён (ENABLE), снят только FORCE."""
    assert "ENABLE ROW LEVEL SECURITY" in _students_block()


def test_views_define_expected_set() -> None:
    defined = set(_CREATE_VIEW_RE.findall(_VIEWS))
    assert defined == VIEW_NAMES


def test_views_reference_only_allowed_tables() -> None:
    referenced = set(_FROM_JOIN_RE.findall(_VIEWS))
    assert referenced, "в 04_views.sql не найдено ни одного FROM/JOIN"
    assert referenced <= ALLOWED_TABLES


def test_views_are_aggregates_only() -> None:
    """Каждая вью — ровно один count(...); кроме total у всех есть GROUP BY."""
    assert len(_CREATE_VIEW_RE.findall(_VIEWS)) == len(VIEW_NAMES)
    assert _VIEWS.count("count(") == len(VIEW_NAMES)
    for name in VIEW_NAMES - {"v_students_total"}:
        assert "GROUP BY" in _view_block(name), f"{name}: нет GROUP BY"


def test_views_have_no_pii_columns() -> None:
    """Ни одна вью не упоминает PII-колонки студентов."""
    assert not _PII_RE.search(_VIEWS)


def test_grants_are_per_view_only() -> None:
    """Гранты — поимённые ON v_*; нет ON ALL TABLES (вернул бы users/query_log)."""
    statements = [
        line.strip()
        for line in _VIEWS.splitlines()
        if line.strip() and not line.strip().startswith("--")
    ]
    assert "GRANT SELECT ON ALL TABLES" not in statements
    granted = {name for name in _GRANT_RE.findall(_VIEWS) if name.startswith("v_")}
    assert granted == VIEW_NAMES