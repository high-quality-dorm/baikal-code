"""LLM-клиент: генерация SQL и пересказ результата (OpenAI-совместимый).

Реализация через langchain-openai (ChatOpenAI) поверх OpenAI-совместимого API:
base_url/model/api_key/temperature настраиваются в Settings. Провайдер меняется
конфигом (.env) без изменения кода. Для тестов используется фейк, реализующий
протокол LLMClient.
"""

from __future__ import annotations

import json
from typing import Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import Settings
from app.llm.prompts import ANSWER_SYSTEM_PROMPT, SQL_SYSTEM_PROMPT


class LLMError(Exception):
    """Ошибка обращения к LLM (не сконфигурирован, недоступен и т.п.)."""


class LLMClient(Protocol):
    """Интерфейс LLM, которым пользуется конвейер (для фейков в тестах)."""

    async def generate_sql(
        self, question: str, schema: str, role: str | None
    ) -> str: ...

    async def answer(
        self,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[list[object]],
    ) -> str: ...


def _text(content: object) -> str:
    """Строковое представление ответа ChatOpenAI (str или список блоков)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content)


def _extract_sql(text: str) -> str:
    """Извлекает SQL из ответа LLM (снимает markdown-обёртку ```sql ... ```)."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # первая строка — ```sql / ```; последняя — закрывающий ```
        body = lines[1:]
        if body and body[-1].strip() == "```":
            body = body[:-1]
        return "\n".join(body).strip()
    return stripped


class ChatLLM:
    """LLM-клиент на langchain-openai; клиент создаётся лениво при вызове."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _client(self) -> ChatOpenAI:
        s = self._settings
        if not s.llm_model or not s.llm_api_key:
            raise LLMError(
                "LLM не сконфигурирован: заполните LLM_MODEL и LLM_API_KEY в .env"
            )
        return ChatOpenAI(
            model=s.llm_model,
            api_key=s.llm_api_key,
            base_url=s.llm_base_url or None,
            temperature=s.llm_temperature,
        )

    async def generate_sql(self, question: str, schema: str, role: str | None) -> str:
        """Возвращает SQL по вопросу и схеме (роль не участвует в промпте)."""
        llm = self._client()
        messages = [
            SystemMessage(content=SQL_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Схема базы данных (роль {role or 'гость'}):\n"
                    f"{schema}\n\n"
                    f"Вопрос пользователя: {question}"
                )
            ),
        ]
        response = await llm.ainvoke(messages)
        sql = _extract_sql(_text(response.content))
        if not sql:
            raise LLMError("LLM вернул пустой SQL")
        return sql

    async def answer(
        self,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[list[object]],
    ) -> str:
        """Пересказывает результат запроса по-русски."""
        llm = self._client()
        result_text = json.dumps({"columns": columns, "rows": rows}, ensure_ascii=False)
        messages = [
            SystemMessage(content=ANSWER_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Вопрос пользователя: {question}\n"
                    f"Выполненный SQL:\n{sql}\n\n"
                    f"Результат:\n{result_text}"
                )
            ),
        ]
        response = await llm.ainvoke(messages)
        return _text(response.content).strip()


__all__ = ["ChatLLM", "LLMClient", "LLMError"]
