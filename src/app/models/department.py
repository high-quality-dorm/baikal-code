from pydantic import BaseModel, Field


class Departments(BaseModel):
    """Кафедры."""

    department_id: int | None = None
    title: str = Field(min_length=1, max_length=150)
    faculty: str = Field(min_length=1, max_length=100)


class Roles(BaseModel):
    """Роли сотрудников."""

    id: int | None = None
    title: str = Field(min_length=1, max_length=50)


class Staff(BaseModel):
    """Сотрудники / преподаватели."""

    staff_id: int | None = None
    full_name: str = Field(min_length=1, max_length=150)
    role_id: int | None = None
    department_id: int | None = None
