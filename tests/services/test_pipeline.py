"""Тесты конвейера text-to-SQL (фейк LLM + фейк шлюз)."""

from __future__ import annotations

import pytest
from db.gateway import GatewayError
from db.models import (
    ColumnInfo,
    ForeignKey,
    Identity,
    QueryResult,
    SchemaDescription,
    TableInfo,
)

from app.api.schemas import Answer
from app.llm.render import schema_to_text
from app.services.pipeline import Pipeline
from tests.fakes import FakeGateway


class FakeLLM:
    """Фейк LLM: детерминированный SQL и пересказ."""

    async def generate_sql(
        self, question: str, schema: str, role: str | None
    ) -> str:
        return "SELECT count(*) FROM students"

    async def answer(
        self,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[list[object]],
    ) -> str:
        return "Ответ"


def _schema() -> SchemaDescription:
    return SchemaDescription(
        identity=Identity(user_id=1, student_id=7, staff_id=None),
        tables=[
            TableInfo(
                name="students",
                title="Профили студентов",
                description="Профили студентов.",
                primary_key=["id"],
                foreign_keys=[
                    ForeignKey(
                        column="group_id",
                        references_table="groups",
                        references_column="id",
                    )
                ],
                columns=[
                    ColumnInfo(name="id", type="integer", nullable=False),
                    ColumnInfo(
                        name="name",
                        type="character varying",
                        nullable=True,
                        sensitive=True,
                    ),
                ],
            )
        ],
    )


def _gateway() -> FakeGateway:
    gw = FakeGateway()
    gw.schema = _schema()
    gw.result = QueryResult(
        columns=["count"],
        rows=[[7]],
        row_count=1,
        truncated=False,
        duration_ms=12.3,
    )
    return gw


@pytest.mark.anyio
async def test_ask_full_flow():
    gw = _gateway()
    pipeline = Pipeline(gw, FakeLLM())

    answer = await pipeline.ask("Сколько студентов?", 1, "student")

    assert isinstance(answer, Answer)
    assert answer.text == "Ответ"
    assert answer.meta.sql == "SELECT count(*) FROM students"
    assert answer.meta.row_count == 1
    assert answer.meta.truncated is False
    assert answer.meta.duration_ms == 12.3
    assert gw.get_schema_calls == [1]
    assert gw.execute_calls == [("SELECT count(*) FROM students", 1)]


@pytest.mark.anyio
async def test_ask_guest_uses_none():
    gw = _gateway()
    pipeline = Pipeline(gw, FakeLLM())

    answer = await pipeline.ask("Сколько мест?", None, None)

    assert answer.meta.sql == "SELECT count(*) FROM students"
    assert gw.get_schema_calls == [None]
    assert gw.execute_calls == [("SELECT count(*) FROM students", None)]


@pytest.mark.anyio
async def test_ask_gateway_error_propagates():
    gw = _gateway()
    gw.gateway_error = GatewayError("Доступ запрещён")
    pipeline = Pipeline(gw, FakeLLM())

    with pytest.raises(GatewayError):
        await pipeline.ask("Сколько студентов?", 1, "student")


def test_schema_to_text_renders_identity_and_tables():
    text = schema_to_text(_schema())
    assert "user_id=1" in text
    assert "Таблица students" in text
    assert "[PII]" in text
    assert "FK: group_id -> groups.id" in text


def test_schema_to_text_guest():
    text = schema_to_text(SchemaDescription(identity=None, tables=[]))
    assert "гость" in text