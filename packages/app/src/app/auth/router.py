"""HTTP-роутер аутентификации и управления учётными записями."""

from __future__ import annotations

from typing import Annotated

from db_mcp.roles import BusinessRole
from fastapi import APIRouter, Depends, HTTPException

from app.auth.deps import AuthContext, get_current_user, require_role
from app.auth.schemas import (
    LoginRequest,
    TokenResponse,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services.auth import (
    AdminExistsError,
    AuthenticationError,
    AuthService,
    DuplicateLoginError,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _service_dep() -> AuthService:
    """Возвращает сервис auth; переопределяется в create_app для общего инстанса."""
    raise NotImplementedError


ServiceDep = Annotated[AuthService, Depends(_service_dep)]
CurrentUser = Annotated[AuthContext, Depends(get_current_user)]


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, service: ServiceDep):
    try:
        return await service.authenticate(data.email, data.password)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@router.post("/bootstrap-admin", response_model=UserOut, status_code=200)
async def bootstrap_admin(data: LoginRequest, service: ServiceDep):
    try:
        return await service.bootstrap_admin(data.email, data.password)
    except AdminExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post(
    "/users",
    response_model=UserOut,
    status_code=201,
    dependencies=[Depends(require_role(BusinessRole.ADMIN))],
)
async def create_user(data: UserCreate, service: ServiceDep):
    try:
        return await service.create_user(data)
    except DuplicateLoginError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get(
    "/users",
    response_model=list[UserOut],
    dependencies=[Depends(require_role(BusinessRole.ADMIN))],
)
async def list_users(service: ServiceDep):
    return await service.list_users()


@router.get("/users/me", response_model=UserOut)
async def my_user(ctx: CurrentUser, service: ServiceDep):
    user_id = int(ctx.user_id) if ctx.user_id and ctx.user_id.isdigit() else None
    user = await service.get_user(user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


@router.patch(
    "/users/{user_id}",
    response_model=UserOut,
    dependencies=[Depends(require_role(BusinessRole.ADMIN))],
)
async def update_user(user_id: int, data: UserUpdate, service: ServiceDep):
    user = await service.update_user(user_id, data)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


@router.delete(
    "/users/{user_id}",
    status_code=204,
    dependencies=[Depends(require_role(BusinessRole.ADMIN))],
)
async def deactivate_user(user_id: int, service: ServiceDep):
    ok = await service.deactivate_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
