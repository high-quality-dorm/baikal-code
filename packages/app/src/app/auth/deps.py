"""FastAPI-зависимости аутентификации.

JWT несёт только `sub` = номер учётки (users.id). Идентичность и бизнес-роль
резолвятся на каждый запрос через пакет db (`resolve_identity`/`resolve_role`):
роль всегда свежая, а деактивированная учётка получает 401 сразу, а не на
следующем логине.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.context import Context
from app.core.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    """Идентичность текущего пользователя из JWT (роль резолвится свежей).

    `can_see_pii` — доступ к персональным данным студентов: True, если у
    пользователя есть RLS-скоуп (resolve_identity не None). Не роль строкой:
    скоуп ограничивает сам RLS.
    """

    user_id: int | None = None
    role: str | None = None
    can_see_pii: bool = False


def _decode_user_id(credentials: HTTPAuthorizationCredentials) -> int | None:
    """Декодирует JWT и возвращает номер учётки (users.id) или None."""
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    if isinstance(sub, str) and sub.isdigit():
        return int(sub)
    return None


async def _resolve_auth(ctx: Context, user_id: int) -> AuthContext:
    """Резолвит идентичность и роль; отсутствующая/неактивная учётка — 401."""
    identity = await ctx.gateway.resolve_identity(user_id)
    if identity is None:
        raise HTTPException(
            status_code=401, detail="Учётная запись не найдена или деактивирована"
        )
    role = await ctx.gateway.resolve_role(user_id)
    return AuthContext(
        user_id=user_id,
        role=role,
        can_see_pii=identity is not None,
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    ctx: Context,
) -> AuthContext:
    """Требует валидный токен активной учётки; иначе 401."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    user_id = _decode_user_id(credentials)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Невалидный или просроченный токен")
    return await _resolve_auth(ctx, user_id)


async def get_optional_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    ctx: Context,
) -> AuthContext:
    """То же, но аноним при отсутствии/невалидном токене (для публичных эндпоинтов).

    Валидный токен неактивной/удалённой учётки — 401 (не молчаливый гость).
    """
    if credentials is None:
        return AuthContext()
    user_id = _decode_user_id(credentials)
    if user_id is None:
        return AuthContext()
    return await _resolve_auth(ctx, user_id)
