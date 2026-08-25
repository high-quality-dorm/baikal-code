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


def test_user_create_accepts_internal_id():
    user = UserCreate(
        email="a@b.c",
        password="password",
        role=BusinessRole.STUDENT,
        internal_id=42,
    )
    assert user.internal_id == 42


@pytest.mark.parametrize("bad", [0, -1])
def test_user_create_rejects_non_positive_internal_id(bad: int):
    with pytest.raises(ValidationError):
        UserCreate(
            email="a@b.c",
            password="password",
            role=BusinessRole.STUDENT,
            internal_id=bad,
        )


def test_user_create_internal_id_defaults_to_none():
    user = UserCreate(email="a@b.c", password="password", role=BusinessRole.ADMIN)
    assert user.internal_id is None


def test_user_out_optional_fields():
    u = UserOut(id=1, external_id="ext", role="student", is_active=True)
    assert u.email is None
    assert u.internal_id is None
