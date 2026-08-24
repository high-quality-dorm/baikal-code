"""Тесты маршрутизации доступа по ролям (без реального подключения к БД)."""

from __future__ import annotations

import asyncio

import pytest

from db_mcp.access import (
    ADMIN,
    APPLICANT,
    BUSINESS_ROLES,
    STUDENT,
    TEACHER,
    Pools,
    UnknownRoleError,
    connection_for,
)
from db_mcp.settings import Settings


def test_business_roles_defined() -> None:
    assert BUSINESS_ROLES == {APPLICANT, STUDENT, TEACHER, ADMIN}


def test_unknown_role_rejected_before_connecting() -> None:
    pools = Pools(Settings())

    async def _connect(role: str) -> None:
        async with connection_for(pools, role, "1"):
            pass  # pragma: no cover

    with pytest.raises(UnknownRoleError):
        asyncio.run(_connect("hacker"))
    with pytest.raises(UnknownRoleError):
        asyncio.run(_connect(""))