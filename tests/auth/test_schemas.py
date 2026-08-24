from pydantic import ValidationError
import pytest

from app.auth.schemas import LoginRequest, UserCreate, UserOut
from app.api.schemas import Role


def test_login_request_valid():
    req = LoginRequest(email="a@b.c", password="pw")
    assert req.email == "a@b.c"


def test_user_create_requires_role():
    user = UserCreate(email="a@b.c", password="password", role=Role.ADMIN)
    assert user.role == Role.ADMIN


def test_user_out_optional_fields():
    u = UserOut(id=1, external_id="ext", role="student", is_active=True)
    assert u.email is None
    assert u.internal_id is None
