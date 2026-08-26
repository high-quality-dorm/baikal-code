"""Фасад пакета db — единая точка входа для приложения.

Инкапсулирует пулы соединений, резолюцию identity, маскирование схемы,
валидацию, исполнение с RLS-контекстом и аудит. Приложение не ходит в базу
напрямую — только через этот фасад.

Роль строкой нигде не передаётся: `get_schema`/`execute_query` принимают только
`user_id` (номер учётки users.id), а скоуп выводится из student_id/staff_id
пользователя (RLS в БД). `resolve_role` — отдельная функция для app-уровня
(логин, require_role).
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import asyncpg

from db.access import Pools, connection_for
from db.audit import Auditor
from db.identity import resolve_identity, resolve_role
from db.models import Identity, QueryResult, SchemaDescription, UserRecord
from db.schema import SchemaBuilder
from db.settings import Settings
from db.userstore import UserStore
from db.validate import MAX_ROWS, validate


class GatewayError(Exception):
    """Ошибка шлюза: валидация SQL, RLS, таймаут."""


class Gateway:
    """Единая точка доступа к базе данных через пакет db."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._pools = Pools(self._settings)
        self._schema = SchemaBuilder(self._pools)
        self._auditor = Auditor(self._pools)
        self._users = UserStore(self._pools)

    async def resolve_identity(self, user_id: int) -> Identity | None:
        """Идентичность пользователя (student_id/staff_id) или None."""
        return await resolve_identity(self._pools, user_id)

    async def resolve_role(self, user_id: int) -> str | None:
        """Бизнес-роль пользователя для app-уровня (student или должность)."""
        return await resolve_role(self._pools, user_id)

    async def get_schema(self, user_id: int | None) -> SchemaDescription:
        """Маскированное описание схемы под пользователя (для LLM).

        user_id=None (гость) — таблицы students/marks отсутствуют, identity None.
        """
        identity = await resolve_identity(self._pools, user_id)
        tables = await self._schema.describe(identity)
        return SchemaDescription(identity=identity, tables=tables)

    async def execute_query(self, sql: str, user_id: int | None) -> QueryResult:
        """Валидировать, исполнить с RLS-контекстом и зааудитировать запрос.

        user_id — номер учётки (users.id) или None для гостя. Роль не передаётся:
        скоуп выводится из student_id/staff_id пользователя политиками RLS.
        """
        started = time.perf_counter()
        error: str | None = None
        row_count = 0
        limit_applied = False
        try:
            validated = validate(sql)
            limit_applied = validated.limit_applied
            identity = await resolve_identity(self._pools, user_id)
            async with connection_for(self._pools, identity) as conn:
                records = await conn.fetch(validated.sql)
            columns, rows = _serialize_records(records)
            row_count = len(rows)
        except Exception as exc:
            error = str(exc)
            raise GatewayError(error) from exc
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            await self._auditor.record(
                role=None,
                user_id=None if user_id is None else str(user_id),
                sql_query=sql,
                status="error" if error else "ok",
                row_count=None if error else row_count,
                error=error,
                duration_ms=round(duration_ms, 3),
            )
        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=row_count,
            truncated=limit_applied and row_count >= MAX_ROWS,
            duration_ms=round(duration_ms, 3),
        )

    # --- Учётные записи (auth) ---

    async def get_user_by_login(self, login: str) -> UserRecord | None:
        """Учётка по логину (email)."""
        return await self._users.get_by_email(login)

    async def get_user(self, user_id: int) -> UserRecord | None:
        """Учётка по id."""
        return await self._users.find(user_id)

    async def list_users(self) -> list[UserRecord]:
        """Все учётки."""
        return await self._users.all()

    async def create_user(
        self,
        *,
        email: str,
        password_hash: str,
        student_id: int | None = None,
        staff_id: int | None = None,
    ) -> UserRecord:
        """Создать учётку (student_id/staff_id опциональны)."""
        return await self._users.create(
            email=email,
            password_hash=password_hash,
            student_id=student_id,
            staff_id=staff_id,
        )

    async def update_user(
        self,
        user_id: int,
        *,
        email: str | None = None,
        password_hash: str | None = None,
        student_id: int | None = None,
        staff_id: int | None = None,
        is_active: bool | None = None,
    ) -> UserRecord | None:
        """Обновить учётку (непустые поля)."""
        return await self._users.update(
            user_id,
            email=email,
            password_hash=password_hash,
            student_id=student_id,
            staff_id=staff_id,
            is_active=is_active,
        )

    async def deactivate_user(self, user_id: int) -> bool:
        """Мягко деактивировать учётку."""
        return await self._users.deactivate(user_id)

    async def has_admin(self) -> bool:
        """Есть ли учётка, связанная с должностью admin."""
        return await self._users.has_admin()

    async def close(self) -> None:
        """Закрыть все пулы соединений."""
        await self._pools.close()


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


__all__ = ["Gateway", "GatewayError"]
