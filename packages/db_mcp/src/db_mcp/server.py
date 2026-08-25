"""MCP-сервер db_mcp — единственный шлюз к базе данных.

Точка входа: `uv run db-mcp` (см. `db-mcp = "db_mcp.server:main"`).
Транспорт по умолчанию — stdio: приложение (packages/app) вызывает шлюз
через MCP и не имеет прямого доступа к базе.

Инструменты:
- get_schema(role) — маскированное под роль описание схемы для LLM;
- execute_query(sql, role, user_id) — валидация, резолюция identity
  (user_id = номер учётки users.id -> internal_id), исполнение с
  RLS-контекстом и аудит в query_log.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg
from mcp.server import MCPServer

from db_mcp.access import Pools, connection_for
from db_mcp.audit import Auditor
from db_mcp.schema import SchemaBuilder
from db_mcp.settings import Settings
from db_mcp.userstore import UserStore
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
        # Строка вместо float: без потери точности для numeric
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return str(value)


def _serialize_records(
    records: Sequence[asyncpg.Record],
) -> tuple[list[str], list[list[object]]]:
    """Колонки и строки результата без потери информации.

    `record.keys()` сохраняет порядок колонок и их дубли (например, при
    `SELECT *` из JOIN двух таблиц с одинаковыми именами колонок), а строки
    строятся по позициям — в отличие от `dict(record)`, который дубли молча
    теряет.
    """
    if not records:
        return [], []
    columns = list(records[0].keys())
    rows = [[_jsonable(value) for value in record] for record in records]
    return columns, rows


def _user_to_dict(user: Any) -> dict[str, object] | None:
    """UserRecord -> dict (None для отсутствующей учётки)."""
    if user is None:
        return None
    return {
        "id": user.id,
        "external_id": user.external_id,
        "email": user.email,
        "password_hash": user.password_hash,
        "role": user.role,
        "internal_id": user.internal_id,
        "display_name": user.display_name,
        "is_active": user.is_active,
    }


def _param_str(params: dict[str, object], key: str) -> str:
    """Типизированное чтение обязательного строкового параметра manage_user."""
    value = params[key]
    if not isinstance(value, str):
        raise TypeError(f"Параметр {key} должен быть строкой")
    return value


def _param_int(params: dict[str, object], key: str) -> int:
    """Типизированное чтение обязательного целочисленного параметра."""
    value = params[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Параметр {key} должен быть целым числом")
    return value


def _param_opt_str(params: dict[str, object], key: str) -> str | None:
    """Необязательный строковый параметр (None, если не передан)."""
    value = params.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"Параметр {key} должен быть строкой")
    return value


def _param_opt_int(params: dict[str, object], key: str) -> int | None:
    """Необязательный целочисленный параметр (None, если не передан)."""
    value = params.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Параметр {key} должен быть целым числом")
    return value


def _param_opt_bool(params: dict[str, object], key: str) -> bool | None:
    """Необязательный булев параметр (None, если не передан)."""
    value = params.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError(f"Параметр {key} должен быть булевым")
    return value


class Gateway:
    """Бизнес-логика шлюза: исполнение запросов и описание схемы."""

    def __init__(self, settings: Settings) -> None:
        self._pools = Pools(settings)
        self._schema = SchemaBuilder(self._pools)
        self._auditor = Auditor(self._pools)
        self._users = UserStore(self._pools)

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
            columns, rows = _serialize_records(records)
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
                "columns": columns,
                "rows": rows,
                "row_count": row_count,
                "truncated": limit_applied and row_count >= MAX_ROWS,
                "duration_ms": round(duration_ms, 3),
            },
            ensure_ascii=False,
        )

    async def manage_user(self, action: str, **params: object) -> str:
        """Управление учётными записями (users) для auth.

        Все запросы — жёстко параметризованные, внутренний контракт приложения
        со шлюзом (не произвольный SQL). Работает через служебную роль
        app_service. Ответ — JSON.
        """
        if action == "get_credentials":
            user = await self._users.get_credentials(_param_str(params, "login"))
            return json.dumps(_user_to_dict(user), ensure_ascii=False)
        if action == "find":
            user = await self._users.find(_param_int(params, "user_id"))
            return json.dumps(_user_to_dict(user), ensure_ascii=False)
        if action == "list":
            users = await self._users.all()
            return json.dumps([_user_to_dict(u) for u in users], ensure_ascii=False)
        if action == "create":
            user = await self._users.create(
                external_id=_param_str(params, "external_id"),
                email=_param_opt_str(params, "email"),
                password_hash=_param_str(params, "password_hash"),
                role=_param_str(params, "role"),
                internal_id=_param_opt_int(params, "internal_id"),
                display_name=_param_opt_str(params, "display_name"),
            )
            return json.dumps(_user_to_dict(user), ensure_ascii=False)
        if action == "update":
            user = await self._users.update(
                _param_int(params, "user_id"),
                email=_param_opt_str(params, "email"),
                password_hash=_param_opt_str(params, "password_hash"),
                role=_param_opt_str(params, "role"),
                internal_id=_param_opt_int(params, "internal_id"),
                display_name=_param_opt_str(params, "display_name"),
                is_active=_param_opt_bool(params, "is_active"),
            )
            return json.dumps(_user_to_dict(user), ensure_ascii=False)
        if action == "deactivate":
            ok = await self._users.deactivate(_param_int(params, "user_id"))
            return json.dumps({"ok": ok}, ensure_ascii=False)
        raise ValueError(f"Неизвестное действие manage_user: {action!r}")


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
        description=(
            "Исполнить read-only SQL-запрос с RLS-контекстом роли и записать его в аудит. "
            "Параметр user_id — это номер учётки (users.id, он же sub из JWT), а не "
            "доменный internal_id: шлюз сам резолвит его в internal_id (student_id/staff_id) "
            "через служебную роль app_service и использует его как RLS-контекст. В query_log "
            "пишется именно users.id."
        ),
    )
    async def execute_query_tool(sql: str, role: str, user_id: str) -> str:
        return await gateway.execute_query(sql, role, user_id)

    @server.tool(
        name="manage_user",
        description=(
            "Управление учётными записями приложения (таблица users) для auth. "
            "Действия (action): get_credentials(login), find(user_id), list(), "
            "create(external_id, email, password_hash, role, internal_id, display_name), "
            "update(user_id, email, password_hash, role, internal_id, display_name, is_active), "
            "deactivate(user_id). Неиспользуемые для действия поля не передаются (None). "
            "Работает через служебную роль app_service; все запросы — фиксированные "
            "параметризованные, а не произвольный SQL. Используется приложением как "
            "реальное хранилище учёток."
        ),
    )
    async def manage_user_tool(
        action: str,
        login: str | None = None,
        user_id: int | None = None,
        external_id: str | None = None,
        email: str | None = None,
        password_hash: str | None = None,
        role: str | None = None,
        internal_id: int | None = None,
        display_name: str | None = None,
        is_active: bool | None = None,
    ) -> str:
        return await gateway.manage_user(
            action,
            login=login,
            user_id=user_id,
            external_id=external_id,
            email=email,
            password_hash=password_hash,
            role=role,
            internal_id=internal_id,
            display_name=display_name,
            is_active=is_active,
        )

    return server


def main() -> None:
    """Точка входа CLI: запуск MCP-сервера на stdio."""
    server = build_server()
    server.run("stdio")


if __name__ == "__main__":
    main()
