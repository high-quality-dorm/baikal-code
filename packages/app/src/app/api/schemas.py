"""API-схемы приложения: то, что приходит и уходит через HTTP.

Роль и идентификатор пользователя передаются заголовками (X-Role, X-User-Id)
и обрабатываются в auth; здесь — только типы тел запроса/ответа.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Role(str, Enum):
    """Роль пользователя в системе."""

    APPLICANT = "applicant"  # абитуриент
    STUDENT = "student"  # студент
    TEACHER = "teacher"  # преподаватель
    ADMIN = "admin"  # ректор, декан, сотрудники и администрация


class Question(BaseModel):
    """Вопрос пользователя к базе данных."""

    text: str = Field(
        min_length=1, max_length=2000, description="Вопрос на естественном языке"
    )


class QueryMeta(BaseModel):
    """Служебная информация о выполненном запросе."""

    sql: str | None = None
    row_count: int = 0
    truncated: bool = False
    duration_ms: float | None = None


class Answer(BaseModel):
    """Ответ приложения: понятный текст + метаданные."""

    text: str
    meta: QueryMeta = Field(default_factory=QueryMeta)
