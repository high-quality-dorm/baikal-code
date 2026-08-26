"""Чтение и запись учётных записей (`users`) для auth.

Выполняется через служебную роль app_service (права только на users и
query_log; на доменные таблицы прав нет). Все запросы — жёстко
параметризованные, никакой интерполяции пользовательских данных: это не
произвольный SQL, а фиксированный внутренний контракт между приложением и
шлюзом, поэтому read-only валидатор (validate.py) не применяется.

Роль строкой не хранится; `student_id`/`staff_id` — необязательные независимые
«расширители» доступа. DELETE сознательно не реализован: деактивация учётки
мягкая (is_active = FALSE), а роль app_service не имеет права на DELETE ON users.
"""

from __future__ import annotations

import logging
from typing import Any

from db.access import Pools
from db.models import UserRecord

logger = logging.getLogger(__name__)

_USER_COLUMNS = "id, student_id, staff_id, email, password_hash, is_active"

_SELECT_BY_EMAIL = f"""
    SELECT {_USER_COLUMNS} FROM users WHERE email = $1
"""
_SELECT_BY_ID = f"""
    SELECT {_USER_COLUMNS} FROM users WHERE id = $1
"""
_SELECT_ALL = f"""
    SELECT {_USER_COLUMNS} FROM users ORDER BY id
"""
_INSERT_SQL = """
    INSERT INTO users (student_id, staff_id, email, password_hash, is_active)
    VALUES ($1, $2, $3, $4, $5)
    RETURNING id
"""
_UPDATE_SQL = """
    UPDATE users SET
        student_id = $1, staff_id = $2, email = $3,
        password_hash = $4, is_active = $5
    WHERE id = $6
"""
_DEACTIVATE_SQL = """
    UPDATE users SET is_active = FALSE WHERE id = $1
"""
_HAS_ADMIN_SQL = """
    SELECT EXISTS (
        SELECT 1 FROM users u
        JOIN staff s ON s.id = u.staff_id
        JOIN positions p ON p.id = s.position_id
        WHERE p.title = 'admin'
    )
"""


class UserStoreError(Exception):
    """Базовая ошибка хранилища учёток."""


class DuplicateLoginError(UserStoreError):
    """Логин (email) уже занят."""


def _to_record(row: Any) -> UserRecord:
    """Собрать UserRecord из asyncpg-записи (по позициям _USER_COLUMNS)."""
    return UserRecord(
        id=row[0],
        student_id=row[1],
        staff_id=row[2],
        email=row[3],
        password_hash=row[4],
        is_active=bool(row[5]),
    )


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

    async def get_by_email(self, email: str) -> UserRecord | None:
        """Учётка по email (логину) или None."""
        row = await self._row(_SELECT_BY_EMAIL, email)
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
        email: str,
        password_hash: str,
        student_id: int | None,
        staff_id: int | None,
    ) -> UserRecord:
        """Создать учётку и вернуть её (с присвоенным id).

        student_id/staff_id необязательны: могут быть оба или ни одного.
        """
        pool = await self._pools.service()
        async with pool.acquire() as conn:
            try:
                user_id = await conn.fetchval(
                    _INSERT_SQL,
                    student_id,
                    staff_id,
                    email,
                    password_hash,
                    True,
                )
            except Exception as exc:
                if _is_unique_violation(exc):
                    raise DuplicateLoginError("Логин уже занят") from exc
                raise
        return UserRecord(
            id=user_id,
            student_id=student_id,
            staff_id=staff_id,
            email=email,
            password_hash=password_hash,
            is_active=True,
        )

    async def update(
        self,
        user_id: int,
        *,
        email: str | None,
        password_hash: str | None,
        student_id: int | None,
        staff_id: int | None,
        is_active: bool | None,
    ) -> UserRecord | None:
        """Обновить учётку (непустые поля); вернуть обновлённую или None."""
        current = await self.find(user_id)
        if current is None:
            return None
        new_student = student_id if student_id is not None else current.student_id
        new_staff = staff_id if staff_id is not None else current.staff_id
        new_email = email if email is not None else current.email
        new_hash = password_hash if password_hash is not None else current.password_hash
        new_active = is_active if is_active is not None else current.is_active
        await self._execute(
            _UPDATE_SQL,
            new_student,
            new_staff,
            new_email,
            new_hash,
            new_active,
            user_id,
        )
        return UserRecord(
            id=user_id,
            student_id=new_student,
            staff_id=new_staff,
            email=new_email,
            password_hash=new_hash,
            is_active=new_active,
        )

    async def deactivate(self, user_id: int) -> bool:
        """Мягко деактивировать учётку (is_active = FALSE)."""
        if await self.find(user_id) is None:
            return False
        await self._execute(_DEACTIVATE_SQL, user_id)
        return True

    async def has_admin(self) -> bool:
        """Есть ли учётка, связанная с сотрудником на должности admin."""
        pool = await self._pools.service()
        async with pool.acquire() as conn:
            return bool(await conn.fetchval(_HAS_ADMIN_SQL))


def _is_unique_violation(exc: Exception) -> bool:
    """Определяет нарушение UNIQUE-ограничения по коду 23505."""
    code = getattr(exc, "sqlstate", None) or getattr(
        getattr(exc, "args", [None])[0], "sqlstate", None
    )
    return code == "23505"
