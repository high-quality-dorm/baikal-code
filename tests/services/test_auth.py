"""Тесты AuthService поверх фейкового шлюза."""

from __future__ import annotations

import pytest

from app.core.security import decode_access_token, hash_password
from app.services.auth import AuthenticationError, AuthService
from db.models import Identity, UserRecord
from tests.fakes import FakeGateway

pytestmark = pytest.mark.usefixtures("rsa_keys")


def _service() -> tuple[AuthService, FakeGateway]:
    gw = FakeGateway()
    return AuthService(gw), gw


def _add(
    gw: FakeGateway,
    user_id: int = 1,
    email: str = "a@b.c",
    password: str = "pw123456",
    is_active: bool = True,
    role: str = "student",
    student_id: int | None = 7,
    staff_id: int | None = None,
) -> None:
    gw.add_user(
        UserRecord(
            id=user_id,
            student_id=student_id,
            staff_id=staff_id,
            email=email,
            password_hash=hash_password(password),
            is_active=is_active,
        ),
        identity=Identity(
            user_id=user_id, student_id=student_id, staff_id=staff_id
        ),
        role=role,
    )


@pytest.mark.anyio
async def test_authenticate_success():
    svc, gw = _service()
    _add(gw)
    token = await svc.authenticate("a@b.c", "pw123456")
    assert decode_access_token(token.access_token)["sub"] == "1"


@pytest.mark.anyio
async def test_authenticate_normalizes_email():
    svc, gw = _service()
    _add(gw)
    token = await svc.authenticate("  A@B.c ", "pw123456")
    assert token.access_token


@pytest.mark.anyio
async def test_authenticate_wrong_password():
    svc, gw = _service()
    _add(gw)
    with pytest.raises(AuthenticationError):
        await svc.authenticate("a@b.c", "badpass")


@pytest.mark.anyio
async def test_authenticate_inactive():
    svc, gw = _service()
    _add(gw, is_active=False)
    with pytest.raises(AuthenticationError):
        await svc.authenticate("a@b.c", "pw123456")


@pytest.mark.anyio
async def test_authenticate_unknown_login():
    svc, gw = _service()
    with pytest.raises(AuthenticationError):
        await svc.authenticate("nobody", "whatever1")


@pytest.mark.anyio
async def test_get_me_returns_record_with_role():
    svc, gw = _service()
    _add(gw, role="admin", student_id=None, staff_id=1)
    me = await svc.get_me(1)
    assert me is not None
    assert me.id == 1
    assert me.email == "a@b.c"
    assert me.role == "admin"
    assert me.staff_id == 1


@pytest.mark.anyio
async def test_get_me_unknown_returns_none():
    svc, gw = _service()
    assert await svc.get_me(99) is None