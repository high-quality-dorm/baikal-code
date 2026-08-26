"""Тесты HTTP-роутера auth: вход и /users/me."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.context import AppContext, get_context
from app.core.security import hash_password
from app.main import create_app
from app.services.auth import AuthService
from app.services.pipeline import Pipeline
from db.models import Identity, UserRecord
from tests.fakes import FakeGateway, StubLLM

pytestmark = pytest.mark.usefixtures("rsa_keys")


def _make_client(gw: FakeGateway) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_context] = lambda: AppContext(
        gateway=gw, auth=AuthService(gw), pipeline=Pipeline(gw, StubLLM())
    )
    return TestClient(app)


def _gateway_with_admin() -> FakeGateway:
    gw = FakeGateway()
    gw.add_user(
        UserRecord(
            id=5,
            student_id=None,
            staff_id=1,
            email="demo_admin@example.com",
            password_hash=hash_password("password123"),
            is_active=True,
        ),
        identity=Identity(user_id=5, student_id=None, staff_id=1),
        role="admin",
    )
    return gw


def _login_headers(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "demo_admin@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_login_success():
    client = _make_client(_gateway_with_admin())
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "demo_admin@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"


def test_login_wrong_password():
    client = _make_client(_gateway_with_admin())
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "demo_admin@example.com", "password": "wrongpass"},
    )
    assert resp.status_code == 401


def test_login_unknown_email():
    client = _make_client(_gateway_with_admin())
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "password123"},
    )
    assert resp.status_code == 401


def test_users_me():
    client = _make_client(_gateway_with_admin())
    headers = _login_headers(client)
    resp = client.get("/api/v1/auth/users/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 5
    assert body["role"] == "admin"
    assert body["staff_id"] == 1


def test_users_me_requires_auth():
    client = _make_client(_gateway_with_admin())
    resp = client.get("/api/v1/auth/users/me")
    assert resp.status_code == 401