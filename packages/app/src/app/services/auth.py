"""Сервис аутентификации поверх пакета db (Gateway).

Учётные записи заводятся вне приложения (сид / руками в БД): сервис только
проверяет логин/пароль и выдаёт JWT, а также отдаёт данные текущей учётки.
"""

from __future__ import annotations

from db.gateway import Gateway

from app.auth.schemas import Me, TokenResponse
from app.core.security import create_access_token, verify_password

# Заглушка bcrypt-хэша для выравнивания времени ответа при неизвестном логине,
# неактивной учётке или отсутствии хэша пароля (защита от timing-оракла).
_DUMMY_HASH = "$2b$12$QP7uqiL9MzVEZ7g728jYJOAjPP.BRIEA5HoEHLXZrNvc3A5dV/CCW"


class AuthenticationError(Exception):
    """Неверные учётные данные."""


def _normalize_email(email: str) -> str:
    """Логин — email: без пробелов и в нижнем регистре."""
    return email.strip().lower()


class AuthService:
    """Оркестрирует вход и выдачу данных текущей учётки."""

    def __init__(self, gateway: Gateway) -> None:
        self._gateway = gateway

    async def authenticate(self, login: str, password: str) -> TokenResponse:
        """Проверяет email/пароль и выдаёт JWT (sub = номер учётки)."""
        record = await self._gateway.get_user_by_login(_normalize_email(login))
        if record is None or not record.is_active or not record.password_hash:
            # Всегда делаем bcrypt-сравнение, чтобы время ответа не зависело
            # от того, существует ли учётка / активна ли она / есть ли хэш.
            verify_password(password, _DUMMY_HASH)
            raise AuthenticationError("Неверный логин или пароль")
        if not verify_password(password, record.password_hash):
            raise AuthenticationError("Неверный логин или пароль")
        token = create_access_token(subject=str(record.id))
        return TokenResponse(access_token=token)

    async def get_me(self, user_id: int) -> Me | None:
        """Учётка с производной ролью для интерфейса (или None)."""
        record = await self._gateway.get_user(user_id)
        if record is None:
            return None
        role = await self._gateway.resolve_role(user_id)
        return Me(
            id=record.id,
            email=record.email,
            student_id=record.student_id,
            staff_id=record.staff_id,
            role=role,
            is_active=record.is_active,
        )
