from pydantic import ValidationError
import pytest

from db_mcp.roles import BusinessRole

from app.auth.schemas import LoginRequest, UserCreate, UserOut


def test_login_request_valid():
    req = LoginRequest(email="a@b.c", password="pw")
    assert req.email == "a@b.c"


def test_user_create_requires_role():
    user = UserCreate(email="a@b.c", password="password", role=BusinessRole.ADMIN)
    assert user.role is BusinessRole.ADMIN


def test_user_out_optional_fields():
    u = UserOut(id=1, external_id="ext", role="student", is_active=True)
    assert u.email is None
    assert u.internal_id is None
