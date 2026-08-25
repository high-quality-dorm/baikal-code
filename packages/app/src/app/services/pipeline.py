"""Конвейер text-to-SQL: вопрос -> SQL -> исполнение через шлюз -> ответ по-русски.

Поток: схема под роль (get_schema) -> генерация SQL через LLM -> исполнение
через шлюз db_mcp с RLS-контекстом (user_id = номер учётки) -> пересказ
результата по-русски вторым LLM-вызовом -> Answer с метаданными запроса.

Ошибки шлюза (GatewayError) и LLM (LLMError) пробрасываются наверх без ретрая
LLM: сгенерированный SQL не переспрашивается, ответ — понятная HTTP-ошибка.
"""

from __future__ import annotations

from app.api.schemas import Answer, QueryMeta
from app.gateway import GatewayClient
from app.llm import LLMClient


class Pipeline:
    """Собирает ответ пользователю из LLM и шлюза db_mcp."""

    def __init__(self, gateway: GatewayClient, llm: LLMClient) -> None:
        self._gateway = gateway
        self._llm = llm

    async def close(self) -> None:
        """Закрывает MCP-сессию шлюза (идемпотентно)."""
        await self._gateway.close()

    async def ask(self, question: str, role: str, user_id: str) -> Answer:
        """Отвечает на вопрос пользователя (role + users.id из JWT)."""
        schema = await self._gateway.get_schema(role)
        sql = await self._llm.generate_sql(question, schema, role)
        result = await self._gateway.execute_query(sql, role, user_id)
        columns: list[str] = result["columns"]
        rows: list[list[object]] = result["rows"]
        text = await self._llm.answer(question, sql, columns, rows)
        return Answer(
            text=text,
            meta=QueryMeta(
                sql=sql,
                row_count=result.get("row_count", 0),
                truncated=result.get("truncated", False),
                duration_ms=result.get("duration_ms"),
            ),
        )


__all__ = ["Pipeline"]
