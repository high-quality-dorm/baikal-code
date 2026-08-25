"""MCP-клиент к шлюзу db_mcp (stdio transport).

Запускает `db_mcp` как подпроцесс (команда из `Settings.db_mcp_command`,
например `uv run db-mcp`) и вызывает его инструменты get_schema / execute_query.
Сессия поднимается лениво при первом обращении и держится открытой, пока
клиент не закрыт — запуск подпроцесса на каждый запрос был бы слишком дорогим.
"""

from __future__ import annotations

import asyncio
import json
import shlex
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class GatewayError(Exception):
    """Ошибка шлюза: is_error от инструмента db_mcp (валидация, RLS, таймаут)."""


class GatewayClient:
    """Клиент к MCP-инструментам шлюза db_mcp."""

    def __init__(self, command: str) -> None:
        parts = shlex.split(command)
        if not parts:
            raise ValueError("db_mcp_command не может быть пустым")
        self._server = StdioServerParameters(command=parts[0], args=parts[1:])
        self._session: ClientSession | None = None
        self._stdio: Any | None = None
        self._lock = asyncio.Lock()

    async def _ensure_session(self) -> ClientSession:
        """Поднимает MCP-сессию при первом обращении (идемпотентно)."""
        if self._session is not None:
            return self._session
        async with self._lock:
            if self._session is not None:
                return self._session
            self._stdio = stdio_client(self._server)
            read_stream, write_stream = await self._stdio.__aenter__()
            session = ClientSession(read_stream, write_stream)
            await session.__aenter__()
            await session.initialize()
            self._session = session
            return session

    async def _call(self, name: str, arguments: dict[str, Any]) -> str:
        """Вызывает инструмент шлюза и возвращает текстовый ответ."""
        session = await self._ensure_session()
        result = await session.call_tool(name, arguments)
        if getattr(result, "is_error", False):
            raise GatewayError(self._error_text(result))
        return self._error_text(result)

    @staticmethod
    def _error_text(result: Any) -> str:
        """Склеивает текстовое содержимое ответа CallToolResult."""
        content = getattr(result, "content", []) or []
        texts = [c.text for c in content if hasattr(c, "text")]
        return "\n".join(texts) if texts else ""

    async def get_schema(self, role: str) -> str:
        """Маскированное под роль описание схемы (JSON-строка от шлюза)."""
        return await self._call("get_schema", {"role": role})

    async def execute_query(self, sql: str, role: str, user_id: str) -> dict[str, Any]:
        """Исполняет read-only SQL с RLS-контекстом; возвращает распарсенный ответ.

        user_id — номер учётки (users.id); резолюцию в internal_id выполняет шлюз.
        """
        raw = await self._call(
            "execute_query", {"sql": sql, "role": role, "user_id": user_id}
        )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GatewayError(f"Некорректный ответ шлюза: {raw!r}") from exc
        if not isinstance(payload, dict):
            raise GatewayError(f"Некорректный ответ шлюза: {raw!r}")
        return payload

    async def manage_user(self, action: str, **params: Any) -> Any:
        """Вызывает manage_user шлюза; возвращает распарсенный JSON-ответ."""
        raw = await self._call("manage_user", {"action": action, **params})
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GatewayError(f"Некорректный ответ шлюза: {raw!r}") from exc
        return payload

    async def close(self) -> None:
        """Закрывает MCP-сессию и останавливает подпроцесс шлюза."""
        if self._session is not None:
            await self._session.__aexit__(None, None, None)
            self._session = None
        if self._stdio is not None:
            await self._stdio.__aexit__(None, None, None)
            self._stdio = None
