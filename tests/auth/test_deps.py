"""Тесты auth-зависимостей: обязательная и опциональная аутентификация."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth.deps import AuthContext, get_current_user, get_optional_context
from app.core.security import create_access_token
from db.models import Identity, UserRecord
from tests.fakes import FakeGateway, make_context

pytestmark = pytest.mark.usefixtures("rsa_keys")


def _creds(sub: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=create_access_token(subject=sub)
    )


def _gateway_with_user() -> FakeGateway:
    gw = FakeGateway()
    gw.add_user(
        UserRecord(id=1, email="a@b.c", password_hash=None, is_active=True),
        identity=Identity(user_id=1, student_id=7, staff_id=None),
        role="student",
    )
    return gw


@pytest.mark.anyio
async def test_get_current_user_ok():
    ctx = make_context(_gateway_with_user())
    auth = await get_current_user(_creds("1"), ctx)
    assert auth == AuthContext(user_id=1, role="student", can_see_pii=True)


@pytest.mark.anyio
async def test_get_current_user_missing_header():
    ctx = make_context(FakeGateway())
    with pytest.raises(HTTPException) as ei:
        await get_current_user(None, ctx)
    assert ei.value.status_code == 401


@pytest.mark.anyio
async def test_get_current_user_bad_token():
    ctx = make_context(FakeGateway())
    bad = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-jwt")
    with pytest.raises(HTTPException) as ei:
        await get_current_user(bad, ctx)
    assert ei.value.status_code == 401


@pytest.mark.anyio
async def test_get_current_user_inactive_account_is_401():
    # Фейк без identity: resolve_identity даёт None (учётка отсутствует/неактивна).
    ctx = make_context(FakeGateway())
    with pytest.raises(HTTPException) as ei:
        await get_current_user(_creds("1"), ctx)
    assert ei.value.status_code == 401


@pytest.mark.anyio
async def test_can_see_pii_true_with_identity_but_no_role():
    # RLS-скоуп есть (identity), роль строкой неизвестна → PII доступен.
    gw = FakeGateway()
    gw.add_user(
        UserRecord(id=2, email="c@d.e", password_hash=None, is_active=True),
        identity=Identity(user_id=2, student_id=None, staff_id=None),
        role=None,
    )
    ctx = make_context(gw)
    auth = await get_optional_context(_creds("2"), ctx)
    assert auth == AuthContext(user_id=2, role=None, can_see_pii=True)


@pytest.mark.anyio
async def test_can_see_pii_false_for_guest():
    ctx = make_context(FakeGateway())
    auth = await get_optional_context(None, ctx)
    assert auth == AuthContext(user_id=None, role=None, can_see_pii=False)


@pytest.mark.anyio
async def test_get_optional_context_guest_without_token():
    ctx = make_context(FakeGateway())
    auth = await get_optional_context(None, ctx)
    assert auth == AuthContext()


@pytest.mark.anyio
async def test_get_optional_context_guest_with_bad_token():
    ctx = make_context(FakeGateway())
    bad = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-jwt")
    auth = await get_optional_context(bad, ctx)
    assert auth == AuthContext()


@pytest.mark.anyio
async def test_get_optional_context_authed():
    ctx = make_context(_gateway_with_user())
    auth = await get_optional_context(_creds("1"), ctx)
    assert auth == AuthContext(user_id=1, role="student", can_see_pii=True)


@pytest.mark.anyio
async def test_get_optional_context_inactive_is_401():
    ctx = make_context(FakeGateway())
    with pytest.raises(HTTPException) as ei:
        await get_optional_context(_creds("1"), ctx)
    assert ei.value.status_code == 401