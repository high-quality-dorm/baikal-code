from pydantic import BaseModel, Field


class Student(BaseModel):
    """Профиль студента."""

    student_id: int | None = None
    name: str = Field(min_length=1, max_length=30)
    surname: str = Field(min_length=1, max_length=30)
    patronymic: str | None = Field(default=None, max_length=30)
    passport: str = Field(min_length=1, max_length=20)
    specialty_id: int | None = None
    admission_year: int
    status_id: int | None = None


class AcademicRecord(BaseModel):
    """Успеваемость студентов."""

    record_id: int | None = None
    student_id: int
    course_id: int
    grade: float | None = Field(default=None, ge=0, le=5)
    has_debt: bool = False
    semester: int = Field(ge=1)
