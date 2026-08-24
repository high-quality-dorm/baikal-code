from fastapi import HTTPException
import pytest

from app.auth.deps import AuthContext, get_current_user, require_role
from app.core.security import create_access_token


def make_headers(role="admin", user_id="7"):
    token = create_access_token(subject=user_id, role=role, email="a@b.c")
    return {"Authorization": f"Bearer {token}"}


def test_get_current_user_ok():
    ctx = get_current_user(make_headers()["Authorization"])
    assert ctx.role == "admin"
    assert ctx.user_id == "7"


def test_get_current_user_missing_header():
    with pytest.raises(HTTPException) as ei:
        get_current_user(None)
    assert ei.value.status_code == 401


def test_require_role_allows():
    dep = require_role("admin")
    ctx = get_current_user(make_headers(role="admin")["Authorization"])
    assert dep(ctx) is None


def test_require_role_denies():
    dep = require_role("admin")
    ctx = get_current_user(make_headers(role="student")["Authorization"])
    with pytest.raises(HTTPException) as ei:
        dep(ctx)
    assert ei.value.status_code == 403
