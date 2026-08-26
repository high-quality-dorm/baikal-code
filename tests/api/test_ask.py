"""Тесты эндпоинта POST /api/v1/ask (NDJSON-поток, гость разрешён)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from db.gateway import GatewayError
from db.models import Identity, UserRecord
from fastapi.testclient import TestClient

from app.context import AppContext, get_context
from app.core.security import hash_password
from app.main import create_app
from app.services.auth import AuthService
from tests.fakes import FakeGateway, StubLLM

pytestmark = pytest.mark.usefixtures("rsa_keys")


class FakeAgent:
    """Фейк агента: фиксированный поток событий или событие error."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, int | None, str | None, bool]] = []

    async def stream(
        self,
        question: str,
        user_id: int | None,
        role: str | None,
        can_see_pii: bool,
    ) -> AsyncIterator[dict[str, object]]:
        self.calls.append((question, user_id, role, can_see_pii))
        if self.error is not None:
            yield {"type": "error", "message": str(self.error)}
            return
        yield {"type": "status", "stage": "started", "message": "Формирую ответ…"}
        yield {"type": "token", "text": "Найдено 10 записей"}
        yield {
            "type": "done",
            "meta": {
                "sql": "SELECT count(*) FROM x",
                "row_count": 10,
                "truncated": False,
                "duration_ms": 5.0,
            },
        }


def _make_client(
    gw: FakeGateway, error: Exception | None = None
) -> tuple[TestClient, FakeAgent]:
    app = create_app()
    fake = FakeAgent(error)
    ctx = AppContext(gateway=gw, auth=AuthService(gw), agent=fake)
    app.dependency_overrides[get_context] = lambda: ctx
    return TestClient(app), fake


def _gateway_with_user() -> FakeGateway:
    gw = FakeGateway()
    gw.add_user(
        UserRecord(
            id=1,
            email="demo_student@example.com",
            password_hash=hash_password("password123"),
            is_active=True,
        ),
        identity=Identity(user_id=1, student_id=7, staff_id=None),
        role="student",
    )
    return gw


def _events(resp) -> list[dict[str, object]]:
    return [json.loads(line) for line in resp.text.strip().splitlines()]


def test_ask_as_guest():
    client, fake = _make_client(_gateway_with_user())
    resp = client.post("/api/v1/ask", json={"text": "Сколько студентов?"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")
    assert [e["type"] for e in _events(resp)] == ["status", "token", "done"]
    assert fake.calls == [("Сколько студентов?", None, None, False)]


def test_ask_as_authed_user():
    client, fake = _make_client(_gateway_with_user())
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "demo_student@example.com", "password": "password123"},
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    resp = client.post(
        "/api/v1/ask", json={"text": "Сколько студентов?"}, headers=headers
    )

    assert resp.status_code == 200
    events = _events(resp)
    assert events[-1]["type"] == "done"
    assert fake.calls == [("Сколько студентов?", 1, "student", True)]


def test_ask_bad_token_is_guest():
    client, fake = _make_client(_gateway_with_user())
    headers = {"Authorization": "Bearer not-a-jwt"}

    resp = client.post(
        "/api/v1/ask", json={"text": "Сколько студентов?"}, headers=headers
    )

    assert resp.status_code == 200
    assert fake.calls == [("Сколько студентов?", None, None, False)]


def test_ask_error_event():
    client, _ = _make_client(
        _gateway_with_user(), error=GatewayError("Доступ запрещён")
    )
    resp = client.post("/api/v1/ask", json={"text": "Сколько студентов?"})

    assert resp.status_code == 200
    assert _events(resp) == [{"type": "error", "message": "Доступ запрещён"}]


def test_ask_empty_question_is_422():
    client, _ = _make_client(_gateway_with_user())
    resp = client.post("/api/v1/ask", json={"text": ""})
    assert resp.status_code == 422


def test_ask_guest_rate_limited(monkeypatch):
    """Гость исчерпывает лимит → 429, агент не вызывается."""
    from app.api import ask as ask_mod

    monkeypatch.setattr(ask_mod, "settings", type("S", (), {
        "rate_limit_user_requests": 30,
        "rate_limit_guest_requests": 2,
        "rate_limit_window_seconds": 60,
    })())

    client, fake = _make_client(_gateway_with_user())
    for _ in range(2):
        resp = client.post("/api/v1/ask", json={"text": "Сколько студентов?"})
        assert resp.status_code == 200
    resp = client.post("/api/v1/ask", json={"text": "Сколько студентов?"})
    assert resp.status_code == 429
    assert len(fake.calls) == 2


def test_ask_authed_user_rate_limited(monkeypatch):
    """Авторизованный исчерпывает свой лимит → 429."""
    from app.api import ask as ask_mod

    monkeypatch.setattr(ask_mod, "settings", type("S", (), {
        "rate_limit_user_requests": 1,
        "rate_limit_guest_requests": 10,
        "rate_limit_window_seconds": 60,
    })())

    client, fake = _make_client(_gateway_with_user())
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "demo_student@example.com", "password": "password123"},
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    assert client.post(
        "/api/v1/ask", json={"text": "Q"}, headers=headers
    ).status_code == 200
    assert client.post(
        "/api/v1/ask", json={"text": "Q"}, headers=headers
    ).status_code == 429
    assert len(fake.calls) == 1


def test_ask_guest_and_authed_share_limiter(monkeypatch):
    """Гость и авторизованный считаются раздельно (разные ключи)."""
    from app.api import ask as ask_mod

    monkeypatch.setattr(ask_mod, "settings", type("S", (), {
        "rate_limit_user_requests": 30,
        "rate_limit_guest_requests": 1,
        "rate_limit_window_seconds": 60,
    })())

    client, fake = _make_client(_gateway_with_user())
    assert client.post("/api/v1/ask", json={"text": "Q"}).status_code == 200
    assert client.post("/api/v1/ask", json={"text": "Q"}).status_code == 429
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "demo_student@example.com", "password": "password123"},
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    assert client.post(
        "/api/v1/ask", json={"text": "Q"}, headers=headers
    ).status_code == 200
    assert len(fake.calls) == 2