"""Согласованность set-based RLS-политик с моделью доступа.

Новая модель доступа: роль не передаётся строкой, RLS строится от двух GUC —
`app.student_id` и `app.staff_id`. Эти тесты защищают инварианты:
- в политиках не используются `app.role`/`app.user_id` (старая модель);
- используются только `app.student_id`/`app.staff_id`;
- должности (position), на которые ссылаются политики, — известный набор
  (teacher/head/dean/admin из seed-справочника `positions`).
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Должности персонала, из которых выводятся роли (seed + политики RLS)
KNOWN_POSITIONS = frozenset({"teacher", "head", "dean", "admin"})

_RLS = (_REPO_ROOT / "db" / "03_rls.sql").read_text(encoding="utf-8")

# GUC, которые могут читать политики
_GUC_RE = re.compile(r"current_setting\('([^']+)'")
# Должности в политиках: staff.position_id = (SELECT id FROM positions WHERE title = '<...>')
_POSITION_RE = re.compile(r"positions WHERE title = '([^']+)'")


def test_rls_uses_only_set_based_gucs() -> None:
    """Политики RLS читают только app.student_id/app.staff_id.

    Старые GUC app.role (роль строкой) и app.user_id (единый id) не должны
    использоваться — доступ выводится из студенческого/кадрового id.
    """
    gucs = set(_GUC_RE.findall(_RLS))
    assert gucs, "не найдено ни одного current_setting в RLS-политиках"
    assert gucs == {"app.student_id", "app.staff_id"}


def test_rls_no_role_or_user_id_literals() -> None:
    """Нет остатков старой модели: app.role / app.user_id отсутствуют."""
    assert "app.role" not in _RLS
    assert "app.user_id" not in _RLS


def test_rls_positions_are_known() -> None:
    """Должности в политиках (teacher/head/dean/admin) — известный набор."""
    positions = set(_POSITION_RE.findall(_RLS))
    assert positions, "не найдено ни одной должности в RLS-политиках"
    assert positions <= KNOWN_POSITIONS