"""Тул execute_query: обёртка над db.Gateway с identity пользователя.

Единственный тул агента. Тонкая обёртка: валидация SQL (sqlglot), RLS,
маскирование и аудит остаются в шлюзе. Ошибки шлюза возвращаются текстом как
результат тула — LLM видит их и может исправить запрос (самокоррекция).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from db.gateway import Gateway, GatewayError

from app.api.schemas import QueryMeta

# Схема тула для OpenAI function-calling (dict принимается bind_tools как есть).
EXECUTE_QUERY_SCHEMA: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "execute_query",
        "description": (
            "Выполнить read-only SQL-запрос к базе университета. Только SELECT "
            "(можно UNION/INTERSECT/EXCEPT), с LIMIT не более 200 строк."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "read-only SQL-запрос"},
            },
            "required": ["sql"],
        },
    },
}


@dataclass
class ToolResult:
    """Результат вызова тула: контент для LLM и метаданные успешного запроса."""

    content: str
    meta: QueryMeta | None = None


class ToolExecutor:
    """Исполняет тулы с identity конкретного пользователя (RLS в шлюзе).

    role — бизнес-роль пользователя для журнала аудита (пишется в
    query_log.role через шлюз).
    """

    def __init__(self, gateway: Gateway, user_id: int | None, role: str | None) -> None:
        self._gateway = gateway
        self._user_id = user_id
        self._role = role

    async def run(self, name: str, args: object) -> ToolResult:
        """Выполняет тул по имени; ошибки возвращает текстом, а не бросает."""
        if name != "execute_query":
            return ToolResult(content=f"Ошибка: неизвестный тул {name!r}")
        sql = args.get("sql") if isinstance(args, dict) else None
        if not isinstance(sql, str) or not sql.strip():
            return ToolResult(
                content="Ошибка: параметр sql должен быть непустой строкой"
            )
        sql = sql.strip()
        try:
            result = await self._gateway.execute_query(sql, self._user_id, self._role)
        except GatewayError as exc:
            return ToolResult(content=f"Ошибка: {exc}")
        payload = {
            "columns": result.columns,
            "rows": result.rows,
            "row_count": result.row_count,
            "truncated": result.truncated,
            "duration_ms": result.duration_ms,
        }
        meta = QueryMeta(
            sql=sql,
            row_count=result.row_count,
            truncated=result.truncated,
            duration_ms=result.duration_ms,
        )
        return ToolResult(content=json.dumps(payload, ensure_ascii=False), meta=meta)


__all__ = ["EXECUTE_QUERY_SCHEMA", "ToolExecutor", "ToolResult"]
