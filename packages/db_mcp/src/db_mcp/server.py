"""MCP-сервер db_mcp — единственный шлюз к базе данных.

Точка входа: `uv run db-mcp` (см. `db-mcp = "db_mcp.server:main"`).
Транспорт по умолчанию — stdio: приложение (packages/app) вызывает шлюз
через MCP и не имеет прямого доступа к базе.

Инструменты:
- get_schema(role) — маскированное под роль описание схемы для LLM;
- execute_query(sql, role, user_id) — валидация, исполнение с RLS-контекстом
  и аудит в query_log.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from mcp.server import MCPServer

from db_mcp.access import Pools, connection_for
from db_mcp.audit import Auditor
from db_mcp.schema import SchemaBuilder
from db_mcp.settings import Settings
from db_mcp.validate import MAX_ROWS, validate

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def _jsonable(value: object) -> object:
    """Перевести значение из asyncpg в JSON-совместимый тип."""
    if value is None or isinstance(value, (bool, int, str, float)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return str(value)


class Gateway:
    """Бизнес-логика шлюза: исполнение запросов и описание схемы."""

    def __init__(self, settings: Settings) -> None:
        self._pools = Pools(settings)
        self._schema = SchemaBuilder(self._pools)
        self._auditor = Auditor(self._pools)

    async def get_schema(self, role: str) -> str:
        """Маскированное описание схемы для роли (JSON)."""
        tables = await self._schema.describe(role)
        return json.dumps({"role": role, "tables": tables}, ensure_ascii=False)

    async def execute_query(self, sql: str, role: str, user_id: str) -> str:
        """Валидировать, исполнить с RLS-контекстом и зааудитировать запрос."""
        started = time.perf_counter()
        error: str | None = None
        row_count = 0
        limit_applied = False
        try:
            validated = validate(sql)
            limit_applied = validated.limit_applied
            async with connection_for(self._pools, role, user_id) as conn:
                records = await conn.fetch(validated.sql)
            rows = [
                {k: _jsonable(v) for k, v in dict(record).items()} for record in records
            ]
            row_count = len(rows)
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            await self._auditor.record(
                role=role,
                user_id=user_id,
                sql_query=sql,
                status="error" if error else "ok",
                row_count=None if error else row_count,
                error=error,
                duration_ms=round(duration_ms, 3),
            )
        return json.dumps(
            {
                "columns": list(rows[0]) if rows else [],
                "rows": rows,
                "row_count": row_count,
                "truncated": limit_applied and row_count >= MAX_ROWS,
                "duration_ms": round(duration_ms, 3),
            },
            ensure_ascii=False,
        )


def build_server(settings: Settings | None = None) -> MCPServer:
    """Собрать MCP-сервер с инструментами шлюза."""
    gateway = Gateway(settings or Settings())
    server = MCPServer(
        "db-mcp",
        title="db_mcp",
        instructions=(
            "Единственный шлюз к базе данных университета. Запросы принимаются "
            "только как read-only SELECT; контекст доступа задаётся ролью и "
            "идентификатором пользователя (RLS)."
        ),
    )

    @server.tool(
        name="get_schema",
        description="Описание схемы базы данных, маскированное под роль пользователя. "
        "Используется для генерации SQL.",
    )
    async def get_schema_tool(role: str) -> str:
        return await gateway.get_schema(role)

    @server.tool(
        name="execute_query",
        description="Исполнить read-only SQL-запрос с RLS-контекстом роли и записать его в аудит.",
    )
    async def execute_query_tool(sql: str, role: str, user_id: str) -> str:
        return await gateway.execute_query(sql, role, user_id)

    return server


def main() -> None:
    """Точка входа CLI: запуск MCP-сервера на stdio."""
    server = build_server()
    server.run("stdio")


if __name__ == "__main__":
    main()
