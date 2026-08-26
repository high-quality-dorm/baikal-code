"""Тесты тул-агента: стриминг событий, самокоррекция, лимиты и тулы."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

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
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.messages.ai import AIMessageChunk

from app.agent.agent import Agent
from app.agent.tools import ToolExecutor
from app.api.schemas import QueryMeta
from app.llm.render import schema_to_text
from tests.fakes import FakeGateway


def _text_chunk(text: str) -> AIMessageChunk:
    return AIMessageChunk(content=text)


def _tool_chunks(
    *,
    sql: str,
    name: str = "execute_query",
    call_id: str = "call_1",
    split_args: bool = False,
) -> list[AIMessageChunk]:
    """Чанки вызова тула; при split_args JSON-строка args разбита на два чанка."""
    if split_args:
        args_json = json.dumps({"sql": sql})
        half = len(args_json) // 2
        return [
            AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {
                        "name": name,
                        "args": args_json[:half],
                        "id": call_id,
                        "index": 0,
                    }
                ],
            ),
            AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {"args": args_json[half:], "index": 0}
                ],
            ),
        ]
    return [
        AIMessageChunk(
            content="",
            tool_call_chunks=[
                {
                    "name": name,
                    "args": json.dumps({"sql": sql}),
                    "id": call_id,
                    "index": 0,
                }
            ],
        )
    ]


class ScriptedLLM:
    """Фейк LLM: по каждому stream()-вызову отдаёт следующий набор чанков."""

    def __init__(self, *responses: AIMessageChunk | list[AIMessageChunk]) -> None:
        self._responses = [r if isinstance(r, list) else [r] for r in responses]
        self.calls = 0
        self.seen_system: list[str] = []

    async def stream(
        self,
        messages: list[BaseMessage],
        tools: list[dict[str, object]] | None = None,
    ) -> AsyncIterator[AIMessageChunk]:
        self.calls += 1
        system = next(
            (m.content for m in messages if isinstance(m, SystemMessage)), ""
        )
        if isinstance(system, str):
            self.seen_system.append(system)
        index = min(self.calls - 1, len(self._responses) - 1)
        for chunk in self._responses[index]:
            yield chunk


def _schema() -> SchemaDescription:
    return SchemaDescription(
        identity=Identity(user_id=1, student_id=7, staff_id=None),
        tables=[
            TableInfo(
                name="faculties",
                title="Факультеты",
                description="Факультеты университета.",
                primary_key=["id"],
                foreign_keys=[],
                columns=[
                    ColumnInfo(name="id", type="integer", nullable=False),
                    ColumnInfo(
                        name="title", type="character varying", nullable=False
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
        rows=[[5]],
        row_count=5,
        truncated=False,
        duration_ms=3.5,
    )
    return gw


async def _events(
    agent: Agent,
    question: str = "Сколько факультетов?",
    user_id=1,
    role="student",
    can_see_pii=True,
) -> list[dict[str, object]]:
    return [
        event async for event in agent.stream(question, user_id, role, can_see_pii)
    ]


def _types(events: list[dict[str, object]]) -> list[str]:
    return [event["type"] for event in events]


@pytest.mark.anyio
async def test_tool_then_answer_streams_events():
    gw = _gateway()
    llm = ScriptedLLM(
        _tool_chunks(sql="SELECT COUNT(*) FROM faculties;", split_args=True),
        _text_chunk("В базе 5 факультетов."),
    )
    agent = Agent(gw, llm, max_steps=5)

    events = await _events(agent)

    assert _types(events) == [
        "status",
        "status",
        "query",
        "token",
        "done",
    ]
    query = events[2]
    assert query["type"] == "query"
    assert query["sql"] == "SELECT COUNT(*) FROM faculties;"
    assert query["row_count"] == 5
    assert query["duration_ms"] == 3.5
    done = events[-1]
    assert done["meta"] == {
        "sql": "SELECT COUNT(*) FROM faculties;",
        "row_count": 5,
        "truncated": False,
        "duration_ms": 3.5,
    }
    assert gw.execute_calls == [("SELECT COUNT(*) FROM faculties;", 1, "student")]
    assert llm.calls == 2


@pytest.mark.anyio
async def test_self_correction_on_gateway_error():
    gw = _gateway()
    gw.execute_failures = ["DROP TABLE students"]
    llm = ScriptedLLM(
        _tool_chunks(sql="DROP TABLE students"),
        _tool_chunks(sql="SELECT COUNT(*) FROM faculties;", call_id="call_2"),
        _text_chunk("Готово"),
    )
    agent = Agent(gw, llm, max_steps=5)

    events = await _events(agent)

    types = _types(events)
    assert any(
        event["type"] == "status" and event["stage"] == "retry" for event in events
    )
    assert types[-1] == "done"
    assert len(gw.execute_calls) == 2
    assert events[-1]["meta"]["row_count"] == 5


@pytest.mark.anyio
async def test_guest_uses_none_user_id():
    gw = _gateway()
    llm = ScriptedLLM(
        _tool_chunks(sql="SELECT COUNT(*) FROM faculties;"),
        _text_chunk("5"),
    )
    agent = Agent(gw, llm, max_steps=5)

    events = await _events(agent, user_id=None, role=None, can_see_pii=False)

    assert _types(events)[-1] == "done"
    assert gw.execute_calls == [("SELECT COUNT(*) FROM faculties;", None, "guest")]


@pytest.mark.anyio
async def test_can_see_pii_true_allows_pii_in_prompt():
    gw = _gateway()
    llm = ScriptedLLM(
        _tool_chunks(sql="SELECT COUNT(*) FROM faculties;"),
        _text_chunk("5"),
    )
    agent = Agent(gw, llm, max_steps=5)

    await _events(agent, can_see_pii=True)

    assert "можно выбирать" in llm.seen_system[0]
    assert "только обобщения и агрегаты" not in llm.seen_system[0]


@pytest.mark.anyio
async def test_can_see_pii_false_blocks_pii_in_prompt():
    gw = _gateway()
    llm = ScriptedLLM(
        _tool_chunks(sql="SELECT COUNT(*) FROM faculties;"),
        _text_chunk("5"),
    )
    agent = Agent(gw, llm, max_steps=5)

    await _events(agent, can_see_pii=False)

    assert "только обобщения и агрегаты" in llm.seen_system[0]
    assert "можно выбирать" not in llm.seen_system[0]


@pytest.mark.anyio
async def test_max_steps_falls_back_to_tool_less_answer():
    gw = _gateway()
    llm = ScriptedLLM(
        _tool_chunks(sql="SELECT COUNT(*) FROM faculties;"),
        _text_chunk("Финальный ответ"),
    )
    agent = Agent(gw, llm, max_steps=1)

    events = await _events(agent)

    assert _types(events) == ["status", "status", "query", "token", "done"]
    assert llm.calls == 2


@pytest.mark.anyio
async def test_empty_final_answer_is_error():
    gw = _gateway()
    llm = ScriptedLLM(_text_chunk(""))
    agent = Agent(gw, llm, max_steps=5)

    events = await _events(agent)

    assert _types(events) == ["status", "status", "error"]
    assert "пустой" in str(events[-1]["message"])


@pytest.mark.anyio
async def test_unresolved_max_steps_is_error():
    gw = _gateway()
    llm = ScriptedLLM(
        _tool_chunks(sql="SELECT 1"),
        _tool_chunks(sql="SELECT 2", call_id="call_2"),
    )
    agent = Agent(gw, llm, max_steps=1)

    events = await _events(agent)

    assert _types(events) == ["status", "status", "query", "error"]
    assert "не завершил" in str(events[-1]["message"])


@pytest.mark.anyio
async def test_executor_success_returns_json_and_meta():
    gw = _gateway()
    executor = ToolExecutor(gw, 7, "student")

    result = await executor.run("execute_query", {"sql": "SELECT COUNT(*) FROM faculties;"})

    assert result.meta == QueryMeta(
        sql="SELECT COUNT(*) FROM faculties;",
        row_count=5,
        truncated=False,
        duration_ms=3.5,
    )
    payload = json.loads(result.content)
    assert payload["row_count"] == 5
    assert payload["columns"] == ["count"]


@pytest.mark.anyio
async def test_executor_gateway_error_returns_text():
    gw = _gateway()
    gw.execute_failures = ["SELECT bad"]
    executor = ToolExecutor(gw, 7, "student")

    result = await executor.run("execute_query", {"sql": "SELECT bad"})

    assert result.meta is None
    assert result.content.startswith("Ошибка:")


@pytest.mark.anyio
async def test_executor_unknown_tool():
    executor = ToolExecutor(_gateway(), 7, "student")

    result = await executor.run("nope", {})

    assert result.meta is None
    assert "неизвестный тул" in result.content


@pytest.mark.anyio
async def test_executor_invalid_sql_argument():
    executor = ToolExecutor(_gateway(), 7, "student")

    assert (await executor.run("execute_query", {})).content.startswith("Ошибка")
    assert (await executor.run("execute_query", {"sql": "  "})).content.startswith("Ошибка")
    assert (await executor.run("execute_query", {"sql": 123})).content.startswith("Ошибка")


def test_schema_to_text_renders_identity_and_tables():
    text = schema_to_text(_schema())
    assert "user_id=1" in text
    assert "Таблица faculties" in text


def test_schema_to_text_guest():
    text = schema_to_text(SchemaDescription(identity=None, tables=[]))
    assert "гость" in text