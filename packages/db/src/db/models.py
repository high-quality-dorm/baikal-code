"""Pydantic-модели работы с базой данных.

Эти модели описывают контракт шлюза `db` для приложения: результат выполнения
запроса, идентичность пользователя, описание схемы для LLM и учётную запись.
Роль строкой не хранится: доступ выводится из `student_id`/`staff_id`, а скоуп
задаёт RLS.
"""

from __future__ import annotations

from pydantic import BaseModel


class Identity(BaseModel):
    """Идентичность пользователя, вычисленная шлюзом из `users`.

    `user_id` — номер учётки (`users.id`, он же `sub` из JWT). `student_id` и
    `staff_id` — необязательные независимые «расширители» доступа: их наличие
    открывает данные соответствующего студента/сотрудника. Пользователь без
    обоих id (или запрос без user_id) — гость, видит только общую информацию.
    """

    user_id: int
    student_id: int | None = None
    staff_id: int | None = None
    is_active: bool = True


class QueryResult(BaseModel):
    """Результат выполнения read-only запроса.

    `rows` — массив массивов (по позициям колонок), `columns` сохраняет порядок
    и дубли имён. Numeric-значения приходят строками (без потери точности).
    """

    columns: list[str]
    rows: list[list[object]]
    row_count: int
    truncated: bool
    duration_ms: float


class ColumnInfo(BaseModel):
    """Колонка таблицы в описании схемы."""

    name: str
    type: str
    nullable: bool
    description: str | None = None
    sensitive: bool = False


class ForeignKey(BaseModel):
    """Внешний ключ: колонка таблицы и её цель."""

    column: str
    references_table: str
    references_column: str


class TableInfo(BaseModel):
    """Таблица в описании схемы для LLM."""

    name: str
    title: str | None = None
    description: str | None = None
    primary_key: list[str] = []
    foreign_keys: list[ForeignKey] = []
    columns: list[ColumnInfo] = []


class SchemaDescription(BaseModel):
    """Маскированное под пользователя описание схемы для LLM.

    `identity` включается в описание, чтобы LLM мог писать запросы со скоупом
    на собственные id пользователя (например, `WHERE student_id = 7`). Для
    гостя `identity` равен None, а таблицы `students`/`marks` отсутствуют.
    """

    identity: Identity | None = None
    tables: list[TableInfo] = []


class UserRecord(BaseModel):
    """Учётная запись пользователя (`users`).

    Роль не хранится: она выводится динамически из `student_id`/`staff_id`
    (для персонала — из `staff.position`).
    """

    id: int
    student_id: int | None = None
    staff_id: int | None = None
    email: str
    password_hash: str | None = None
    is_active: bool = True
