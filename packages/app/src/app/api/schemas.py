"""API-схемы приложения: то, что приходит и уходит через HTTP.

Роль и идентификатор пользователя передаются заголовками (X-Role, X-User-Id)
и обрабатываются в auth; здесь — только типы тел запроса/ответа.

Роли берутся из канонического вокабуляра db_mcp (`BusinessRole`), а не из
собственного enum: приложение переиспользует единый источник значений.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Question(BaseModel):
    """Вопрос пользователя к базе данных.

    Текст вопроса может нести и контекст беседы: фронтенд вклеивает предыдущие
    реплики в начало текста (см. docs/design.md), поэтому лимит поднят с 2000
    до 100 000 символов — потолок на длинную сессию, но не бесконечность.
    """

    text: str = Field(
        min_length=1, max_length=100_000, description="Вопрос на естественном языке"
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
