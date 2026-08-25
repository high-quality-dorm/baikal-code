"""Согласованность вокабуляра ролей db_mcp с конфигурацией БД (RLS)."""

from __future__ import annotations

import re
from pathlib import Path

from db_mcp.roles import BUSINESS_ROLES

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_rls_role_literals_are_business_roles() -> None:
    """Роли в политиках RLS — подмножество канонических бизнес-ролей."""
    sql = (_REPO_ROOT / "db" / "03_rls.sql").read_text(encoding="utf-8")
    literals = set(
        re.findall(r"current_setting\('app\.role', true\) = '([^']+)'", sql)
    )
    assert literals, "не найдено ни одного литерала роли в RLS-политиках"
    assert literals <= BUSINESS_ROLES
