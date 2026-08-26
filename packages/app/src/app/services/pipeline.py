"""Конвейер text-to-SQL: вопрос -> SQL -> исполнение через пакет db -> ответ.

Поток: схема под пользователя (`get_schema`) -> генерация SQL через LLM ->
исполнение через `db.Gateway` с RLS-контекстом (user_id = номер учётки, гость
= None) -> пересказ результата по-русски вторым LLM-вызовом -> `Answer`.

Ошибки шлюза (GatewayError) и LLM (LLMError) пробрасываются наверх без ретрая
LLM: сгенерированный SQL не переспрашивается, ответ — понятная HTTP-ошибка.
"""

from __future__ import annotations

from db.gateway import Gateway

from app.api.schemas import Answer, QueryMeta
from app.llm import LLMClient
from app.llm.render import schema_to_text


class Pipeline:
    """Собирает ответ пользователю из LLM и шлюза db."""

    def __init__(self, gateway: Gateway, llm: LLMClient) -> None:
        self._gateway = gateway
        self._llm = llm

    async def ask(self, question: str, user_id: int | None, role: str | None) -> Answer:
        """Отвечает на вопрос пользователя (user_id=None — гость)."""
        schema = await self._gateway.get_schema(user_id)
        sql = await self._llm.generate_sql(question, schema_to_text(schema), role)
        result = await self._gateway.execute_query(sql, user_id)
        text = await self._llm.answer(question, sql, result.columns, result.rows)
        return Answer(
            text=text,
            meta=QueryMeta(
                sql=sql,
                row_count=result.row_count,
                truncated=result.truncated,
                duration_ms=result.duration_ms,
            ),
        )


__all__ = ["Pipeline"]
