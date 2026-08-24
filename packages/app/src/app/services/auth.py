"""Сервис аутентификации: вход, bootstrap-админ, управление учётками.

Зависит от UserCredentialsStore (реальная реализация — через db_mcp, потом).
"""

from __future__ import annotations

from app.auth.schemas import (
    Credentials,
    TokenResponse,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.services.providers import UserCredentialsStore

# Заглушка bcrypt-хэша для выравнивания времени ответа при неизвестном логине,
# неактивной учётке или отсутствии хэша пароля (защита от timing-оракла).
_DUMMY_HASH = "$2b$12$QP7uqiL9MzVEZ7g728jYJOAjPP.BRIEA5HoEHLXZrNvc3A5dV/CCW"


class AuthError(Exception):
    """Базовая ошибка auth."""


class AuthenticationError(AuthError):
    """Неверные учётные данные."""


class AdminExistsError(AuthError):
    """Админ уже существует (bootstrap невозможен)."""


class DuplicateLoginError(AuthError):
    """Логин уже занят."""


class AuthService:
    """Оркестрирует аутентификацию и управление учётными записями."""

    def __init__(self, store: UserCredentialsStore) -> None:
        self.store = store

    async def authenticate(self, login: str, password: str) -> TokenResponse:
        """Проверяет логин/пароль и выдаёт JWT."""
        creds = await self.store.get_credentials(login)
        if creds is None or not creds.is_active or not creds.password_hash:
            # Всегда делаем bcrypt-сравнение, чтобы время ответа не зависело
            # от того, существует ли учётка / активна ли она / есть ли хэш.
            verify_password(password, _DUMMY_HASH)
            raise AuthenticationError("Неверный логин или пароль")
        if not verify_password(password, creds.password_hash):
            raise AuthenticationError("Неверный логин или пароль")
        assert creds.id is not None, "creds from store always have an id"
        token = create_access_token(
            subject=str(creds.id),
            role=creds.role,
            email=creds.email,
        )
        return TokenResponse(access_token=token, role=creds.role)

    async def bootstrap_admin(self, email: str, password: str) -> UserOut:
        """Создаёт первого админа, только если админов ещё нет."""
        all_users = await self.list_users()
        if any(u.role == "admin" for u in all_users):
            raise AdminExistsError("Админ уже существует")
        return await self.create_user(
            UserCreate(email=email, password=password, role="admin")
        )

    async def create_user(self, data: UserCreate) -> UserOut:
        """Создаёт учётку (email и external_id уникальны)."""
        existing = await self.store.get_credentials(data.email)
        if existing is not None:
            raise DuplicateLoginError("Логин уже занят")
        if data.external_id is not None:
            external = await self.store.get_credentials(data.external_id)
            if external is not None:
                raise DuplicateLoginError("Логин уже занят")
        user = await self.store.persist(
            Credentials(
                id=None,
                external_id=data.external_id or f"user-{data.email}",
                email=data.email,
                password_hash=hash_password(data.password),
                role=data.role.value,
                display_name=data.display_name,
                is_active=True,
            )
        )
        return self._to_out(user)

    async def list_users(self) -> list[UserOut]:
        """Возвращает все учётки."""
        return [self._to_out(c) for c in await self.store.all()]

    async def get_user(self, user_id: int) -> UserOut | None:
        """Возвращает учётку по id или None."""
        user = await self.store.find(user_id)
        return self._to_out(user) if user else None

    async def update_user(self, user_id: int, data: UserUpdate) -> UserOut | None:
        """Обновляет учётку; при смене пароля перехеширует его."""
        user = await self.store.find(user_id)
        if user is None:
            return None
        if data.role is not None:
            user.role = data.role.value
        if data.is_active is not None:
            user.is_active = data.is_active
        if data.display_name is not None:
            user.display_name = data.display_name
        if data.password is not None:
            user.password_hash = hash_password(data.password)
        await self.store.persist(user)
        return self._to_out(user)

    async def deactivate_user(self, user_id: int) -> bool:
        """Деактивирует учётку (мягкое удаление)."""
        user = await self.store.find(user_id)
        if user is None:
            return False
        user.is_active = False
        await self.store.persist(user)
        return True

    @staticmethod
    def _to_out(user: Credentials) -> UserOut:
        assert user.id is not None, "persisted users always have an id"
        return UserOut(
            id=user.id,
            email=user.email,
            external_id=user.external_id,
            role=user.role,
            internal_id=user.internal_id,
            display_name=user.display_name,
            is_active=user.is_active,
        )
