from pydantic import ValidationError
import pytest

from app.auth.schemas import LoginRequest, Me, TokenResponse


def test_login_request_valid():
    req = LoginRequest(email="a@b.c", password="pw")
    assert req.email == "a@b.c"


def test_login_request_requires_fields():
    with pytest.raises(ValidationError):
        LoginRequest()


def test_token_response_defaults_to_bearer():
    token = TokenResponse(access_token="abc")
    assert token.token_type == "bearer"


def test_me_optional_links_and_role_default_to_none():
    me = Me(id=1, email="a@b.c")
    assert me.student_id is None
    assert me.staff_id is None
    assert me.role is None
    assert me.is_active is True


def test_me_with_links_and_role():
    me = Me(id=2, email="a@b.c", student_id=7, staff_id=None, role="student")
    assert me.student_id == 7
    assert me.role == "student"