"""Тесты маршрутизации доступа по ролям (без реального подключения к БД)."""

from __future__ import annotations

import asyncio

import pytest

from db_mcp.access import (
    Pools,
    UnknownRoleError,
    _as_business_role,
    connection_for,
)
from db_mcp.roles import BUSINESS_ROLES, BusinessRole, DbPool
from db_mcp.settings import Settings


def test_business_roles_defined() -> None:
    assert BUSINESS_ROLES == {"applicant", "student", "teacher", "admin"}


def test_business_role_values_match_enum() -> None:
    assert BUSINESS_ROLES == {role.value for role in BusinessRole}


def test_as_business_role_normalizes() -> None:
    assert _as_business_role("student") is BusinessRole.STUDENT
    assert _as_business_role(BusinessRole.ADMIN) is BusinessRole.ADMIN


def test_as_business_role_rejects_unknown() -> None:
    with pytest.raises(UnknownRoleError):
        _as_business_role("hacker")
    with pytest.raises(UnknownRoleError):
        _as_business_role("")


def test_pool_for_role_maps_all_business_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Каждая бизнес-роль отображается на ожидаемый пул PostgreSQL."""
    pools = Pools(Settings())
    resolved: list[DbPool] = []

    async def fake_get(_self: Pools, db_pool: DbPool) -> object:
        resolved.append(db_pool)
        return object()

    monkeypatch.setattr(Pools, "_get", fake_get)

    async def run() -> None:
        await pools.pool_for_role("applicant")
        await pools.pool_for_role(BusinessRole.STUDENT)
        await pools.pool_for_role("teacher")
        await pools.pool_for_role(BusinessRole.ADMIN)

    asyncio.run(run())
    assert resolved == [DbPool.RO, DbPool.RO, DbPool.RO, DbPool.ADMIN]


def test_unknown_role_rejected_before_connecting() -> None:
    pools = Pools(Settings())

    async def _connect(role: str | BusinessRole) -> None:
        async with connection_for(pools, role, "1"):
            pass  # pragma: no cover

    with pytest.raises(UnknownRoleError):
        asyncio.run(_connect("hacker"))
    with pytest.raises(UnknownRoleError):
        asyncio.run(_connect(""))
