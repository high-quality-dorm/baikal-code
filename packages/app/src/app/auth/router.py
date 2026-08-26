"""HTTP-роутер аутентификации: вход и данные текущей учётки."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.auth.deps import AuthContext, get_current_user
from app.auth.schemas import LoginRequest, Me, TokenResponse
from app.context import Context
from app.services.auth import AuthenticationError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

CurrentUser = Annotated[AuthContext, Depends(get_current_user)]


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, ctx: Context) -> TokenResponse:
    """Вход по email/паролю; роль не включается в токен — она резолвится."""
    try:
        return await ctx.auth.authenticate(data.email, data.password)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@router.get("/users/me", response_model=Me)
async def my_user(user: CurrentUser, ctx: Context) -> Me:
    """Текущая учётка с производной ролью (для бейджа в интерфейсе)."""
    if user.user_id is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    me = await ctx.auth.get_me(user.user_id)
    if me is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return me
