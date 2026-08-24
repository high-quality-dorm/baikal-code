from pydantic import BaseModel, Field


class Specialty(BaseModel):
    """Специальности / направления подготовки."""

    specialty_id: int | None = None
    code: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=150)
    faculty: str = Field(min_length=1, max_length=100)
    total_semesters: int = Field(default=8, ge=1)


class StudentStatus(BaseModel):
    """Справочник статусов студентов."""

    status_id: int | None = None
    title: str = Field(min_length=1, max_length=50)
