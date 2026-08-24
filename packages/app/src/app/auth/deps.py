"""FastAPI-зависимости аутентификации и проверки ролей."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException

from app.core.security import decode_access_token


@dataclass
class AuthContext:
    """Идентичность текущего пользователя из JWT."""

    user_id: str | None = None
    role: str | None = None
    email: str | None = None


def get_current_user(authorization: str | None = Header(default=None)) -> AuthContext:
    """Разбирает Bearer-токен; при отсутствии/невалидности — 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Невалидный или просроченный токен")
    return AuthContext(
        user_id=payload.get("sub"),
        role=payload.get("role"),
        email=payload.get("email"),
    )


def get_optional_context(
    authorization: str | None = Header(default=None),
) -> AuthContext:
    """То же, но аноним при отсутствии/невалидном токене (для публичных эндпоинтов)."""
    if not authorization or not authorization.startswith("Bearer "):
        return AuthContext()
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        return AuthContext()
    return AuthContext(
        user_id=payload.get("sub"),
        role=payload.get("role"),
        email=payload.get("email"),
    )


def require_role(*roles: str) -> Callable[..., None]:
    """Возвращает зависимость, требующую одну из указанных ролей (иначе 403).

    Текущий пользователь берётся из Bearer-токена через get_current_user,
    поэтому require_role можно передавать напрямую в Depends.
    """

    def checker(ctx: Annotated[AuthContext, Depends(get_current_user)]) -> None:
        if not ctx.role or ctx.role not in roles:
            raise HTTPException(status_code=403, detail="Недостаточно прав")

    return checker
