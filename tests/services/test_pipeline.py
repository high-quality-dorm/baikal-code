"""Тесты конвейера text-to-SQL (фейк LLM + фейк шлюз)."""

from __future__ import annotations

import pytest

from app.api.schemas import Answer
from app.gateway import GatewayError
from app.services.pipeline import Pipeline


class FakeGateway:
    """Фейк шлюза db_mcp: запоминает вызовы, отдаёт фиксированный результат."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, str, str]] = []
        self.schema_calls: list[str] = []

    async def get_schema(self, role: str) -> str:
        self.schema_calls.append(role)
        return '{"role": "student", "tables": []}'

    async def execute_query(self, sql: str, role: str, user_id: str) -> dict:
        self.calls.append((sql, role, user_id))
        if self.error is not None:
            raise self.error
        return {
            "columns": ["student_id"],
            "rows": [[7]],
            "row_count": 1,
            "truncated": False,
            "duration_ms": 12.3,
        }

    async def close(self) -> None:
        pass


class FakeLLM:
    """Фейк LLM: детерминированный SQL и пересказ."""

    async def generate_sql(self, question: str, schema: str, role: str) -> str:
        return "SELECT student_id FROM students"

    async def answer(
        self,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[list[object]],
    ) -> str:
        return "Нашёл одного студента"


@pytest.mark.anyio
async def test_ask_full_flow() -> None:
    gateway = FakeGateway()
    pipeline = Pipeline(gateway, FakeLLM())

    answer = await pipeline.ask("Сколько студентов?", "student", "3")

    assert isinstance(answer, Answer)
    assert answer.text == "Нашёл одного студента"
    assert answer.meta.sql == "SELECT student_id FROM students"
    assert answer.meta.row_count == 1
    assert answer.meta.truncated is False
    assert answer.meta.duration_ms == 12.3
    assert gateway.schema_calls == ["student"]
    assert gateway.calls == [("SELECT student_id FROM students", "student", "3")]


@pytest.mark.anyio
async def test_ask_gateway_error_propagates() -> None:
    gateway = FakeGateway(error=GatewayError("Доступ запрещён"))
    pipeline = Pipeline(gateway, FakeLLM())

    with pytest.raises(GatewayError):
        await pipeline.ask("Сколько студентов?", "student", "3")