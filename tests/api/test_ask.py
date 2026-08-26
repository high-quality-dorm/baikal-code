"""Тесты эндпоинта POST /api/v1/ask: гость и авторизованный."""

from __future__ import annotations

import pytest
from db.gateway import GatewayError
from db.models import Identity, UserRecord
from fastapi.testclient import TestClient

from app.api.schemas import Answer
from app.context import AppContext, get_context
from app.core.security import hash_password
from app.llm import LLMError
from app.main import create_app
from app.services.auth import AuthService
from tests.fakes import FakeGateway, StubLLM

pytestmark = pytest.mark.usefixtures("rsa_keys")


class FakePipeline:
    """Фейк конвейера: фиксированный Answer или заданная ошибка."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, int | None, str | None]] = []

    async def ask(
        self, question: str, user_id: int | None, role: str | None
    ) -> Answer:
        self.calls.append((question, user_id, role))
        if self.error is not None:
            raise self.error
        return Answer(
            text="Найдено 10 записей",
            meta={
                "sql": "SELECT count(*) FROM x",
                "row_count": 10,
                "truncated": False,
                "duration_ms": 5.0,
            },
        )


def _make_client(
    gw: FakeGateway, error: Exception | None = None
) -> tuple[TestClient, FakePipeline]:
    app = create_app()
    fake = FakePipeline(error)
    app.dependency_overrides[get_context] = lambda: AppContext(
        gateway=gw, auth=AuthService(gw), pipeline=fake
    )
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


def test_ask_as_guest():
    client, fake = _make_client(_gateway_with_user())
    resp = client.post("/api/v1/ask", json={"text": "Сколько студентов?"})
    assert resp.status_code == 200
    assert resp.json()["text"] == "Найдено 10 записей"
    assert fake.calls == [("Сколько студентов?", None, None)]


def test_ask_as_authed_user():
    client, fake = _make_client(_gateway_with_user())
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "demo_student@example.com", "password": "password123"},
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    resp = client.post("/api/v1/ask", json={"text": "Сколько студентов?"}, headers=headers)
    assert resp.status_code == 200
    assert fake.calls == [("Сколько студентов?", 1, "student")]


def test_ask_bad_token_is_guest():
    client, fake = _make_client(_gateway_with_user())
    headers = {"Authorization": "Bearer not-a-jwt"}
    resp = client.post("/api/v1/ask", json={"text": "Сколько студентов?"}, headers=headers)
    assert resp.status_code == 200
    assert fake.calls == [("Сколько студентов?", None, None)]


def test_ask_gateway_error_is_502():
    client, _ = _make_client(
        _gateway_with_user(), error=GatewayError("Доступ запрещён")
    )
    resp = client.post("/api/v1/ask", json={"text": "Сколько студентов?"})
    assert resp.status_code == 502
    assert "Доступ запрещён" in resp.json()["detail"]


def test_ask_llm_error_is_502():
    client, _ = _make_client(
        _gateway_with_user(), error=LLMError("LLM не сконфигурирован")
    )
    resp = client.post("/api/v1/ask", json={"text": "Сколько студентов?"})
    assert resp.status_code == 502