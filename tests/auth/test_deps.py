from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import pytest

from db_mcp.roles import BusinessRole

from app.auth.deps import AuthContext, get_current_user, require_role
from app.core.security import create_access_token

pytestmark = pytest.mark.usefixtures("rsa_keys")


def make_credentials(role="admin", user_id="7"):
    token = create_access_token(subject=user_id, role=role, email="a@b.c")
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_get_current_user_ok():
    ctx = get_current_user(make_credentials())
    assert ctx.role == "admin"
    assert ctx.user_id == "7"


def test_get_current_user_missing_header():
    with pytest.raises(HTTPException) as ei:
        get_current_user(None)
    assert ei.value.status_code == 401


def test_require_role_allows():
    dep = require_role(BusinessRole.ADMIN)
    ctx = get_current_user(make_credentials(role="admin"))
    assert dep(ctx) is None


def test_require_role_denies():
    dep = require_role(BusinessRole.ADMIN)
    ctx = get_current_user(make_credentials(role="student"))
    with pytest.raises(HTTPException) as ei:
        dep(ctx)
    assert ei.value.status_code == 403
