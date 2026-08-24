from pydantic import BaseModel, Field


class Course(BaseModel):
    """Учебные дисциплины."""

    course_id: int | None = None
    title: str = Field(min_length=1, max_length=150)
    department_id: int | None = None
    semester: int = Field(ge=1)
    lecture_hours: int = Field(default=0, ge=0)


class CourseInstructor(BaseModel):
    """Назначение преподавателей на курсы."""

    course_id: int
    staff_id: int
