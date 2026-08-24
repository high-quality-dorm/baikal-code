"""Хранилище учётных записей для auth-сервиса.

Реальное хранилище будет получать данные через db_mcp (этап «ядро db_mcp»).
Сейчас используется InMemoryAuthStore (мок) для разработки и тестов.
"""

from __future__ import annotations

from typing import Protocol

from app.auth.schemas import Credentials


class UserCredentialsStore(Protocol):
    """Интерфейс хранилища учётных записей, которым пользуется AuthService."""

    async def get_credentials(self, login: str) -> Credentials | None: ...

    async def find(self, user_id: int) -> Credentials | None: ...

    async def all(self) -> list[Credentials]: ...

    async def persist(self, user: Credentials) -> Credentials: ...


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
