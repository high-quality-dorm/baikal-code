"""Хранилище учётных записей для auth-сервиса.

Реальная реализация (DbUserCredentialsStore) читает/пишет таблицу `users`
через шлюз db_mcp (MCP-инструмент manage_user) — приложение не ходит в базу
напрямую. InMemoryAuthStore оставлен для unit-тестов auth, но в боевом коде
не используется.
"""

from __future__ import annotations

from typing import Protocol

from app.auth.schemas import Credentials
from app.gateway.client import GatewayClient


class UserCredentialsStore(Protocol):
    """Интерфейс хранилища учётных записей, которым пользуется AuthService."""

    async def get_credentials(self, login: str) -> Credentials | None: ...

    async def find(self, user_id: int) -> Credentials | None: ...

    async def all(self) -> list[Credentials]: ...

    async def persist(self, user: Credentials) -> Credentials: ...


def _to_credentials(data: dict | None) -> Credentials | None:
    """Словарь из manage_user -> Credentials (None, если учётки нет)."""
    if data is None:
        return None
    return Credentials(
        id=data.get("id"),
        external_id=data.get("external_id") or "",
        email=data.get("email"),
        password_hash=data.get("password_hash"),
        role=data.get("role") or "",
        internal_id=data.get("internal_id"),
        display_name=data.get("display_name"),
        is_active=bool(data.get("is_active", True)),
    )


class DbUserCredentialsStore:
    """Реальное хранилище учёток поверх шлюза db_mcp (таблица users)."""

    def __init__(self, gateway: GatewayClient) -> None:
        self._gateway = gateway

    async def get_credentials(self, login: str) -> Credentials | None:
        data = await self._gateway.manage_user("get_credentials", login=login)
        return _to_credentials(data)

    async def find(self, user_id: int) -> Credentials | None:
        data = await self._gateway.manage_user("find", user_id=user_id)
        return _to_credentials(data)

    async def all(self) -> list[Credentials]:
        rows = await self._gateway.manage_user("list")
        return [c for r in (rows or []) if (c := _to_credentials(r)) is not None]

    async def persist(self, user: Credentials) -> Credentials:
        if user.id is None:
            data = await self._gateway.manage_user(
                "create",
                external_id=user.external_id,
                email=user.email,
                password_hash=user.password_hash,
                role=user.role,
                internal_id=user.internal_id,
                display_name=user.display_name,
            )
        else:
            data = await self._gateway.manage_user(
                "update",
                user_id=user.id,
                email=user.email,
                password_hash=user.password_hash,
                role=user.role,
                internal_id=user.internal_id,
                display_name=user.display_name,
                is_active=user.is_active,
            )
        result = _to_credentials(data)
        if result is None:
            raise ValueError("manage_user вернул None вместо учётной записи")
        return result


class InMemoryAuthStore:
    """Мок-хранилище учёток в памяти (по id и по логину: email или external_id)."""

    def __init__(self) -> None:
        self._users: dict[int, Credentials] = {}
        self._by_login: dict[str, int] = {}
        self._next_id = 1

    async def add(self, user: Credentials) -> Credentials:
        """Регистрирует учётку (алиас persist, удобен для сидинга в тестах)."""
        return await self.persist(user)

    async def persist(self, user: Credentials) -> Credentials:
        """Сохраняет учётку; присваивает id, если его ещё нет."""
        if user.id is None or user.id == 0:
            user = user.model_copy(update={"id": self._next_id})
            self._next_id += 1
        user_id = user.id
        assert user_id is not None
        self._users[user_id] = user
        if user.email:
            self._by_login[user.email] = user_id
        self._by_login[user.external_id] = user_id
        return user

    async def find(self, user_id: int) -> Credentials | None:
        """Возвращает учётку по id или None."""
        return self._users.get(user_id)

    async def all(self) -> list[Credentials]:
        """Возвращает все учётки."""
        return list(self._users.values())

    async def get_credentials(self, login: str) -> Credentials | None:
        """Возвращает учётку по логину (email или external_id) или None."""
        user_id = self._by_login.get(login)
        if user_id is None:
            return None
        return self._users.get(user_id)
