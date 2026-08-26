"""Тул-агент: цикл LLM-вызовов над db.Gateway со стримингом.

Эмитит NDJSON-события: стадии работы, результаты тула `execute_query` и токены
финального текста (см. ADR 36). Ошибки шлюза (валидация SQL, RLS, лимиты)
возвращаются LLM как результат тула — агент может исправить запрос и повторить.

Каждый шаг LLM стримится через `astream`: текст уходит токенами сразу, а вызовы
тулов собираются из `tool_call_chunks` и исполняются после завершения шага.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from db.gateway import Gateway, GatewayError
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.agent.prompts import build_system_prompt
from app.agent.tools import EXECUTE_QUERY_SCHEMA, ToolExecutor
from app.api.schemas import QueryMeta
from app.llm import ChatLLM, LLMError
from app.llm.render import schema_to_text


class AgentError(Exception):
    """Агент не смог сформировать ответ (пустой ответ, исчерпан лимит шагов)."""


def _content_text(content: object) -> str:
    """Строковое представление содержимого чанка (str или список блоков)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content)


def _merge_tool_calls(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Склеивает tool_call_chunks (по index) в готовые вызовы тулов."""
    by_index: dict[int, dict[str, str]] = {}
    for chunk in chunks:
        index = chunk.get("index") or 0
        entry = by_index.setdefault(index, {"name": "", "args": "", "id": ""})
        if chunk.get("name"):
            entry["name"] += chunk["name"]
        if chunk.get("args"):
            entry["args"] += chunk["args"]
        if chunk.get("id"):
            entry["id"] += chunk["id"]
    calls: list[dict[str, Any]] = []
    for index in sorted(by_index):
        entry = by_index[index]
        try:
            args = json.loads(entry["args"]) if entry["args"].strip() else {}
        except json.JSONDecodeError:
            args = {}
        calls.append(
            {
                "name": entry["name"],
                "args": args,
                "id": entry["id"],
                "type": "tool_call",
            }
        )
    return calls


def _meta_dict(meta: QueryMeta | None) -> dict[str, object]:
    """Словарь метаданных для события done (всегда со всеми полями)."""
    if meta is None:
        return {"sql": None, "row_count": 0, "truncated": False, "duration_ms": None}
    return {
        "sql": meta.sql,
        "row_count": meta.row_count,
        "truncated": meta.truncated,
        "duration_ms": meta.duration_ms,
    }


@dataclass
class _StepOutcome:
    """Итог одного LLM-шага: накопленный текст и собранные вызовы тулов."""

    text: str = ""
    tool_calls: list[dict[str, Any]] | None = None


class Agent:
    """Отвечает на вопрос пользователя, вызывая тулы execute_query в цикле."""

    def __init__(self, gateway: Gateway, llm: ChatLLM, max_steps: int) -> None:
        self._gateway = gateway
        self._llm = llm
        self._max_steps = max_steps

    async def stream(
        self, question: str, user_id: int | None, role: str | None
    ) -> AsyncIterator[dict[str, object]]:
        """Эмитит NDJSON-события: status/query/token/done/error."""
        yield {"type": "status", "stage": "started", "message": "Формирую ответ…"}
        try:
            schema = await self._gateway.get_schema(user_id)
        except GatewayError as exc:
            yield {"type": "error", "message": f"Ошибка шлюза: {exc}"}
            return
        yield {"type": "status", "stage": "schema", "message": "Загружаю схему…"}

        messages: list[BaseMessage] = [
            SystemMessage(content=build_system_prompt(schema_to_text(schema), role)),
            HumanMessage(content=question),
        ]
        executor = ToolExecutor(self._gateway, user_id)
        last_meta: QueryMeta | None = None

        try:
            for _ in range(self._max_steps):
                outcome = _StepOutcome()
                async for event in self._step_stream(
                    messages, [EXECUTE_QUERY_SCHEMA], outcome
                ):
                    yield event
                calls = outcome.tool_calls
                if not calls:
                    if outcome.text:
                        yield {"type": "done", "meta": _meta_dict(last_meta)}
                    else:
                        yield {"type": "error", "message": "LLM вернул пустой ответ"}
                    return
                messages.append(AIMessage(content=outcome.text, tool_calls=calls))
                for call in calls:
                    result = await executor.run(call["name"], call["args"])
                    if result.meta is not None:
                        last_meta = result.meta
                        meta = result.meta
                        yield {
                            "type": "query",
                            "sql": meta.sql,
                            "row_count": meta.row_count,
                            "truncated": meta.truncated,
                            "duration_ms": meta.duration_ms,
                        }
                    elif result.content.startswith("Ошибка"):
                        yield {
                            "type": "status",
                            "stage": "retry",
                            "message": "Запрос не выполнился, исправляю SQL…",
                        }
                    messages.append(
                        ToolMessage(content=result.content, tool_call_id=call["id"])
                    )

            # Исчерпан лимит шагов: финальный вызов без тулов для ответа.
            outcome = _StepOutcome()
            async for event in self._step_stream(messages, None, outcome):
                yield event
            if outcome.tool_calls or not outcome.text:
                yield {
                    "type": "error",
                    "message": f"Агент не завершил ответ за {self._max_steps} шагов",
                }
            else:
                yield {"type": "done", "meta": _meta_dict(last_meta)}
        except AgentError as exc:
            yield {"type": "error", "message": str(exc)}
        except LLMError as exc:
            yield {"type": "error", "message": str(exc)}
        except GatewayError as exc:
            yield {"type": "error", "message": f"Ошибка шлюза: {exc}"}
        except Exception as exc:  # noqa: BLE001
            yield {"type": "error", "message": f"Внутренняя ошибка: {exc}"}

    async def _step_stream(
        self,
        messages: list[BaseMessage],
        tools: list[dict[str, object]] | None,
        outcome: _StepOutcome,
    ) -> AsyncIterator[dict[str, object]]:
        """Один LLM-шаг: стримит токены, собирает текст и вызовы тулов."""
        tool_chunks: list[dict[str, Any]] = []
        async for chunk in self._llm.stream(messages, tools=tools):
            tool_chunks.extend(dict(c) for c in (chunk.tool_call_chunks or []))
            text = _content_text(chunk.content)
            if text:
                outcome.text += text
                yield {"type": "token", "text": text}
        outcome.tool_calls = _merge_tool_calls(tool_chunks)


__all__ = ["Agent", "AgentError"]
