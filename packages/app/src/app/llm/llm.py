"""LLM-клиент: стриминговый вызов OpenAI-совместимого API.

Реализация через langchain-openai (ChatOpenAI): base_url/model/api_key/
temperature настраиваются в Settings. Провайдер меняется конфигом (.env) без
изменения кода. `stream` отдаёт чанки (`AIMessageChunk`) с текстом и
`tool_call_chunks` — их разбирает тул-агент.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

from langchain_core.messages import BaseMessage
from langchain_core.messages.ai import AIMessageChunk
from langchain_openai import ChatOpenAI

from app.core.config import Settings


class LLMError(Exception):
    """Ошибка обращения к LLM (не сконфигурирован, недоступен и т.п.)."""


class ChatLLM:
    """LLM-клиент на langchain-openai; клиент создаётся лениво при вызове."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _client(self, tools: list[dict[str, Any]] | None = None) -> ChatOpenAI:
        s = self._settings
        if not s.llm_model or not s.llm_api_key:
            raise LLMError(
                "LLM не сконфигурирован: заполните LLM_MODEL и LLM_API_KEY в .env"
            )
        llm = ChatOpenAI(
            model=s.llm_model,
            api_key=s.llm_api_key,
            base_url=s.llm_base_url or None,
            temperature=s.llm_temperature,
        )
        return cast(ChatOpenAI, llm.bind_tools(tools)) if tools else llm

    async def stream(
        self,
        messages: list[BaseMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[AIMessageChunk]:
        """Стримит ответ LLM чанками; LLMError — при невалидной конфигурации."""
        llm = self._client(tools)
        async for chunk in llm.astream(messages):
            yield chunk


__all__ = ["ChatLLM", "LLMError"]
