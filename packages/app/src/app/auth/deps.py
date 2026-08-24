"""FastAPI-зависимости аутентификации и проверки ролей."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    """Идентичность текущего пользователя из JWT."""

    user_id: str | None = None
    role: str | None = None
    email: str | None = None


def _context_from_token(token: str) -> AuthContext:
    """Строит AuthContext из декодированного JWT (бросает jwt.PyJWTError)."""
    payload = decode_access_token(token)
    return AuthContext(
        user_id=payload.get("sub"),
        role=payload.get("role"),
        email=payload.get("email"),
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthContext:
    """Разбирает Bearer-токен; при отсутствии/невалидности — 401."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    try:
        return _context_from_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Невалидный или просроченный токен")


def get_optional_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthContext:
    """То же, но аноним при отсутствии/невалидном токене (для публичных эндпоинтов)."""
    if credentials is None:
        return AuthContext()
    try:
        return _context_from_token(credentials.credentials)
    except jwt.PyJWTError:
        return AuthContext()


def require_role(*roles: str) -> Callable[..., None]:
    """Возвращает зависимость, требующую одну из указанных ролей (иначе 403).

    Текущий пользователь берётся из Bearer-токена через get_current_user,
    поэтому require_role можно передавать напрямую в Depends.
    """

    def checker(ctx: Annotated[AuthContext, Depends(get_current_user)]) -> None:
        if not ctx.role or ctx.role not in roles:
            raise HTTPException(status_code=403, detail="Недостаточно прав")

    return checker
