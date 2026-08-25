"""Тесты эндпоинта POST /api/v1/ask (фейк-конвейер через dependency override)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.ask import _pipeline_dep
from app.api.schemas import Answer
from app.gateway import GatewayError
from app.main import create_app
from app.services.providers import InMemoryAuthStore

pytestmark = pytest.mark.usefixtures("rsa_keys")


class FakePipeline:
    """Фейк конвейера: фиксированный Answer или заданная ошибка."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, str, str]] = []

    async def ask(self, question: str, role: str, user_id: str) -> Answer:
        self.calls.append((question, role, user_id))
        if self.error is not None:
            raise self.error
        return Answer(
            text="Найдено 10 записей",
            meta={
                "sql": "SELECT count(*) FROM academic_records",
                "row_count": 10,
                "truncated": False,
                "duration_ms": 5.0,
            },
        )

    async def close(self) -> None:
        pass


def _make_client(error: Exception | None = None) -> tuple[TestClient, dict, FakePipeline]:
    app = create_app(auth_store=InMemoryAuthStore())
    fake = FakePipeline(error=error)
    app.dependency_overrides[_pipeline_dep] = lambda: fake
    client = TestClient(app)
    client.post(
        "/api/v1/auth/bootstrap-admin",
        json={"email": "admin@x.ru", "password": "admin12345"},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@x.ru", "password": "admin12345"},
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    return client, headers, fake


def test_ask_requires_auth() -> None:
    client, _, _ = _make_client()
    resp = client.post("/api/v1/ask", json={"text": "Сколько студентов?"})
    assert resp.status_code == 401


def test_ask_success() -> None:
    client, headers, fake = _make_client()
    resp = client.post(
        "/api/v1/ask", json={"text": "Сколько студентов?"}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "Найдено 10 записей"
    assert body["meta"]["sql"] == "SELECT count(*) FROM academic_records"
    assert body["meta"]["row_count"] == 10
    assert fake.calls == [("Сколько студентов?", "admin", "1")]


def test_ask_gateway_error_is_502() -> None:
    client, headers, _ = _make_client(error=GatewayError("Доступ запрещён"))
    resp = client.post(
        "/api/v1/ask", json={"text": "Сколько студентов?"}, headers=headers
    )
    assert resp.status_code == 502
    assert "Доступ запрещён" in resp.json()["detail"]