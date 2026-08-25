"""Чтение и запись учётных записей (`users`) для auth.

Выполняется через служебную роль app_service (права только на users и
query_log; на доменные таблицы прав нет). Все запросы — жёстко
параметризованные, никакой интерполяции пользовательских данных: это не
произвольный SQL, а фиксированный внутренний контракт между приложением и
шлюзом, поэтому read-only валидатор (validate.py) не применяется.

DELETE сознательно не реализован: деактивация учётки мягкая (is_active =
FALSE), а роль app_service не имеет права на DELETE ON users.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from db_mcp.access import Pools
from db_mcp.roles import BusinessRole

logger = logging.getLogger(__name__)

_USER_COLUMNS = (
    "id, external_id, email, password_hash, role, internal_id, display_name, is_active"
)

_SELECT_BY_LOGIN = f"""
    SELECT {_USER_COLUMNS} FROM users
    WHERE email = $1 OR external_id = $1
"""
_SELECT_BY_ID = f"""
    SELECT {_USER_COLUMNS} FROM users WHERE id = $1
"""
_SELECT_ALL = f"""
    SELECT {_USER_COLUMNS} FROM users ORDER BY id
"""
_INSERT_SQL = """
    INSERT INTO users (external_id, email, password_hash, role, internal_id,
                       display_name, is_active)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    RETURNING id
"""
_UPDATE_SQL = """
    UPDATE users SET
        email = $1, password_hash = $2, role = $3, internal_id = $4,
        display_name = $5, is_active = $6
    WHERE id = $7
"""
_DEACTIVATE_SQL = """
    UPDATE users SET is_active = FALSE WHERE id = $1
"""


class UserStoreError(Exception):
    """Базовая ошибка хранилища учёток."""


class InvalidRoleError(UserStoreError):
    """Неизвестная бизнес-роль."""


class DuplicateLoginError(UserStoreError):
    """Логин (email/external_id) уже занят."""


@dataclass
class UserRecord:
    """Представление учётки, как её отдаёт хранилище (id всегда заполнен)."""

    id: int
    external_id: str
    email: str | None = None
    password_hash: str | None = None
    role: str = ""
    internal_id: int | None = None
    display_name: str | None = None
    is_active: bool = True


def _to_record(row: Any) -> UserRecord:
    """Собрать UserRecord из asyncpg-записи (по позициям _USER_COLUMNS)."""
    return UserRecord(
        id=row[0],
        external_id=row[1],
        email=row[2],
        password_hash=row[3],
        role=row[4],
        internal_id=row[5],
        display_name=row[6],
        is_active=bool(row[7]),
    )


def _validate_role(role: str) -> str:
    """Нормализовать и проверить бизнес-роль; иначе — InvalidRoleError."""
    try:
        return BusinessRole(role).value
    except ValueError:
        raise InvalidRoleError(f"Неизвестная роль: {role!r}") from None


def _validate_internal_id(internal_id: int | None) -> int | None:
    """internal_id должен быть >= 1, если задан."""
    if internal_id is not None and internal_id < 1:
        raise UserStoreError("internal_id должен быть >= 1")
    return internal_id


class UserStore:
    """Хранилище учёток поверх пула служебной роли app_service."""

    def __init__(self, pools: Pools) -> None:
        self._pools = pools

    async def _row(self, sql: str, *args: object) -> Any | None:
        pool = await self._pools.service()
        async with pool.acquire() as conn:
            return await conn.fetchrow(sql, *args)

    async def _rows(self, sql: str, *args: object) -> list[Any]:
        pool = await self._pools.service()
        async with pool.acquire() as conn:
            return list(await conn.fetch(sql, *args))

    async def _execute(self, sql: str, *args: object) -> None:
        pool = await self._pools.service()
        async with pool.acquire() as conn:
            await conn.execute(sql, *args)

    async def get_credentials(self, login: str) -> UserRecord | None:
        """Учётка по логину (email или external_id) или None."""
        row = await self._row(_SELECT_BY_LOGIN, login)
        return _to_record(row) if row else None

    async def find(self, user_id: int) -> UserRecord | None:
        """Учётка по id или None."""
        row = await self._row(_SELECT_BY_ID, user_id)
        return _to_record(row) if row else None

    async def all(self) -> list[UserRecord]:
        """Все учётки, упорядоченные по id."""
        rows = await self._rows(_SELECT_ALL)
        return [_to_record(r) for r in rows]

    async def create(
        self,
        *,
        external_id: str,
        email: str | None,
        password_hash: str,
        role: str,
        internal_id: int | None,
        display_name: str | None,
    ) -> UserRecord:
        """Создать учётку и вернуть её (с присвоенным id)."""
        role = _validate_role(role)
        internal_id = _validate_internal_id(internal_id)
        pool = await self._pools.service()
        async with pool.acquire() as conn:
            try:
                user_id = await conn.fetchval(
                    _INSERT_SQL,
                    external_id,
                    email,
                    password_hash,
                    role,
                    internal_id,
                    display_name,
                    True,
                )
            except Exception as exc:
                if _is_unique_violation(exc):
                    raise DuplicateLoginError("Логин уже занят") from exc
                raise
        return UserRecord(
            id=user_id,
            external_id=external_id,
            email=email,
            password_hash=password_hash,
            role=role,
            internal_id=internal_id,
            display_name=display_name,
            is_active=True,
        )

    async def update(
        self,
        user_id: int,
        *,
        email: str | None,
        password_hash: str | None,
        role: str | None,
        internal_id: int | None,
        display_name: str | None,
        is_active: bool | None,
    ) -> UserRecord | None:
        """Обновить учётку (непустые поля); вернуть обновлённую или None."""
        current = await self.find(user_id)
        if current is None:
            return None
        new_email = email if email is not None else current.email
        new_hash = password_hash if password_hash is not None else current.password_hash
        new_role = role if role is not None else current.role
        new_internal = internal_id if internal_id is not None else current.internal_id
        new_display = display_name if display_name is not None else current.display_name
        new_active = is_active if is_active is not None else current.is_active
        new_role = _validate_role(new_role)
        new_internal = _validate_internal_id(new_internal)
        await self._execute(
            _UPDATE_SQL,
            new_email,
            new_hash,
            new_role,
            new_internal,
            new_display,
            new_active,
            user_id,
        )
        return UserRecord(
            id=user_id,
            external_id=current.external_id,
            email=new_email,
            password_hash=new_hash,
            role=new_role,
            internal_id=new_internal,
            display_name=new_display,
            is_active=new_active,
        )

    async def deactivate(self, user_id: int) -> bool:
        """Мягко деактивировать учётку (is_active = FALSE)."""
        if await self.find(user_id) is None:
            return False
        await self._execute(_DEACTIVATE_SQL, user_id)
        return True


def _is_unique_violation(exc: Exception) -> bool:
    """Определяет нарушение UNIQUE-ограничения по коду 23505."""
    code = getattr(exc, "sqlstate", None) or getattr(
        getattr(exc, "args", [None])[0], "sqlstate", None
    )
    return code == "23505"
