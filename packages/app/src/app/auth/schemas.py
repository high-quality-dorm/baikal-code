"""Pydantic-схемы auth: тела запросов/ответов и данные текущей учётки.

Роль не хранится и в токене не передаётся: JWT несёт только `sub` (номер
учётки users.id), а бизнес-роль вычисляется на каждый запрос через пакет `db`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Тело запроса на вход."""

    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    """Ответ с access-токеном (роль не включается — она резолвится)."""

    access_token: str
    token_type: str = "bearer"


class Me(BaseModel):
    """Текущая учётка: идентичность и производная роль (для интерфейса)."""

    id: int
    email: str
    student_id: int | None = None
    staff_id: int | None = None
    role: str | None = None
    is_active: bool = True
