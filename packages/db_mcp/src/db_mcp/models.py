"""Доменные сущности базы данных.

Эти модели описывают схему БД и используются для генерации сида
и ролевого маскирования описания схемы. PII-поля помечены sensitive=True:
они доступны только роли администрации (app_admin), для остальных ролей
маскируются и не попадают в описание схемы для LLM.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Faculty(BaseModel):
    """Факультет."""

    faculty_id: int | None = None
    title: str = Field(min_length=1, max_length=100)
    dean_id: int | None = None  # ссылка на staff


class Department(BaseModel):
    """Кафедра (принадлежит факультету)."""

    department_id: int | None = None
    title: str = Field(min_length=1, max_length=150)
    faculty_id: int | None = None
    head_id: int | None = None  # заведующий (staff)


class Role(BaseModel):
    """Роль сотрудника."""

    id: int | None = None
    title: str = Field(min_length=1, max_length=50)


class Staff(BaseModel):
    """Сотрудник / преподаватель (ФИО — не PII, выводимо)."""

    staff_id: int | None = None
    full_name: str = Field(min_length=1, max_length=150)
    role_id: int | None = None
    department_id: int | None = None


class Specialty(BaseModel):
    """Направление подготовки."""

    specialty_id: int | None = None
    code: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=150)
    faculty_id: int | None = None
    total_semesters: int = Field(default=8, ge=1)


class StudentStatus(BaseModel):
    """Справочник статусов студентов."""

    status_id: int | None = None
    title: str = Field(min_length=1, max_length=50)


class Group(BaseModel):
    """Учебная группа."""

    group_id: int | None = None
    title: str = Field(min_length=1, max_length=50)
    specialty_id: int | None = None
    admission_year: int | None = None


class Student(BaseModel):
    """Профиль студента (name/surname/patronymic/passport — PII)."""

    student_id: int | None = None
    name: str = Field(min_length=1, max_length=30)  # sensitive
    surname: str = Field(min_length=1, max_length=30)  # sensitive
    patronymic: str | None = Field(default=None, max_length=30)  # sensitive
    passport: str = Field(min_length=1, max_length=20)  # sensitive
    specialty_id: int | None = None
    group_id: int | None = None
    admission_year: int
    status_id: int | None = None


class Course(BaseModel):
    """Учебная дисциплина."""

    course_id: int | None = None
    title: str = Field(min_length=1, max_length=150)
    department_id: int | None = None
    semester: int = Field(ge=1)
    lecture_hours: int = Field(default=0, ge=0)


class CourseInstructor(BaseModel):
    """Назначение преподавателей на курсы."""

    course_id: int
    staff_id: int


class AcademicRecord(BaseModel):
    """Успеваемость студентов."""

    record_id: int | None = None
    student_id: int
    course_id: int
    grade: float | None = Field(default=None, ge=0, le=5)
    has_debt: bool = False
    semester: int = Field(ge=1)


class Room(BaseModel):
    """Аудитория."""

    room_id: int | None = None
    building: str = Field(min_length=1, max_length=50)
    number: str = Field(min_length=1, max_length=20)
    capacity: int = Field(default=0, ge=0)


class ScheduleSlot(BaseModel):
    """Расписание занятий."""

    slot_id: int | None = None
    course_id: int
    group_id: int | None = None
    room_id: int | None = None
    weekday: int = Field(ge=1, le=7)
    period: int = Field(ge=1, le=8)  # номер пары


class AdmissionPlan(BaseModel):
    """Контрольные цифры приёма по годам."""

    plan_id: int | None = None
    year: int
    specialty_id: int
    budget_places: int = Field(default=0, ge=0)
    paid_places: int = Field(default=0, ge=0)
    application_deadline: str | None = None  # дата окончания приёма


class AdmissionStats(BaseModel):
    """Фактическая статистика приёма по годам."""

    stat_id: int | None = None
    year: int
    specialty_id: int
    applications: int = Field(default=0, ge=0)
    enrolled: int = Field(default=0, ge=0)
    passing_score: float | None = None
    avg_score: float | None = None


__all__ = [
    "AcademicRecord",
    "AdmissionPlan",
    "AdmissionStats",
    "Course",
    "CourseInstructor",
    "Department",
    "Faculty",
    "Group",
    "Role",
    "Room",
    "ScheduleSlot",
    "Specialty",
    "Staff",
    "Student",
    "StudentStatus",
]
