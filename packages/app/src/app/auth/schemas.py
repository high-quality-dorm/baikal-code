"""Pydantic-схемы auth: тела запросов/ответов и внутренние данные учётки."""

from __future__ import annotations

from db_mcp.roles import BusinessRole
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Тело запроса на вход."""

    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    """Ответ с access-токеном."""

    access_token: str
    token_type: str = "bearer"
    role: str


class Credentials(BaseModel):
    """Данные учётки, возвращаемые хранилищем (id присваивает хранилище)."""

    id: int | None = None
    email: str | None = None
    external_id: str
    password_hash: str | None = None
    role: str
    internal_id: int | None = None
    display_name: str | None = None
    is_active: bool = True


class UserCreate(BaseModel):
    """Создание учётки админом."""

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: BusinessRole
    external_id: str | None = Field(default=None, max_length=100)
    # Связка с человеком: student_id/staff_id. Задаётся админом вручную;
    # резолюцию в RLS-контекст выполняет шлюз (users.id -> internal_id).
    # Неверный ID не проверяется — даёт пустой доступ по RLS.
    internal_id: int | None = Field(default=None, ge=1)
    display_name: str | None = Field(default=None, max_length=150)


class UserUpdate(BaseModel):
    """Обновление учётки админом (все поля необязательны)."""

    role: BusinessRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=150)


class UserOut(BaseModel):
    """Представление учётки для ответа (без password_hash)."""

    id: int
    email: str | None = None
    external_id: str
    role: str
    internal_id: int | None = None
    display_name: str | None = None
    is_active: bool = True
