"""Описание схемы БД для LLM, маскированное под роль.

Схема читается из живого каталога PostgreSQL (information_schema.columns)
через пул соединений той роли, для которой формируется описание:

- для app_ro (applicant/student/teacher) каталог физически не показывает
  PII-колонки студентов и служебные таблицы (нет привилегий) — маскирование
  происходит на уровне БД;
- для app_admin (admin) виден полный набор колонок, а чувствительные поля
  помечаются флагом `sensitive`, чтобы LLM не выводил их в ответах.

К каталогу добавляются русские описания таблиц и колонок (для генерации
корректного SQL), пометка PII-колонок, а также статические PK/FK из TABLE_META
(для генерации JOIN).
"""

from __future__ import annotations

from collections import defaultdict
from typing import TypedDict

import asyncpg

from db_mcp.access import Pools


class _ForeignKey(TypedDict):
    """Внешний ключ: колонка таблицы и её цель."""

    column: str
    references_table: str
    references_column: str


class _TableMeta(TypedDict):
    """Статическое описание таблицы: заголовок, колонки и ключи.

    PK/FK хранятся здесь (а не читаются из каталога): информация о схеме и
    так хардкодится в TABLE_META, а из БД остаётся брать только фактические
    колонки (маскированные под роль). Содержимое ключей контролируется —
    PII-колонки не могут оказаться PK или целью FK.
    """

    title: str
    description: str
    columns: dict[str, str]
    primary_key: list[str]
    foreign_keys: list[_ForeignKey]


# Служебные таблицы, которые не попадают в описание схемы для LLM
EXCLUDED_TABLES = frozenset({"users", "query_log"})

# PII-колонки студентов: доступны только администрации и не должны выводиться
SENSITIVE_COLUMNS = {
    "students": frozenset({"name", "surname", "patronymic", "passport"}),
}

# Русские описания таблиц и колонок (для генерации SQL и безопасности)
TABLE_META: dict[str, _TableMeta] = {
    "faculties": {
        "title": "Факультеты",
        "description": "Факультеты университета.",
        "primary_key": ["faculty_id"],
        "foreign_keys": [
            {
                "column": "dean_id",
                "references_table": "staff",
                "references_column": "staff_id",
            },
        ],
        "columns": {
            "faculty_id": "Идентификатор факультета",
            "title": "Название факультета",
            "dean_id": "Декан (staff.staff_id)",
        },
    },
    "departments": {
        "title": "Кафедры",
        "description": "Кафедры, входящие в состав факультетов.",
        "primary_key": ["department_id"],
        "foreign_keys": [
            {
                "column": "faculty_id",
                "references_table": "faculties",
                "references_column": "faculty_id",
            },
            {
                "column": "head_id",
                "references_table": "staff",
                "references_column": "staff_id",
            },
        ],
        "columns": {
            "department_id": "Идентификатор кафедры",
            "title": "Название кафедры",
            "faculty_id": "Факультет (faculties.faculty_id)",
            "head_id": "Заведующий кафедрой (staff.staff_id)",
        },
    },
    "roles": {
        "title": "Роли сотрудников",
        "description": "Справочник должностей сотрудников.",
        "primary_key": ["id"],
        "foreign_keys": [],
        "columns": {
            "id": "Идентификатор роли",
            "title": "Название роли",
        },
    },
    "staff": {
        "title": "Сотрудники и преподаватели",
        "description": "Сотрудники и преподаватели университета. ФИО выводимо.",
        "primary_key": ["staff_id"],
        "foreign_keys": [
            {
                "column": "role_id",
                "references_table": "roles",
                "references_column": "id",
            },
            {
                "column": "department_id",
                "references_table": "departments",
                "references_column": "department_id",
            },
        ],
        "columns": {
            "staff_id": "Идентификатор сотрудника",
            "full_name": "ФИО сотрудника",
            "role_id": "Должность (roles.id)",
            "department_id": "Кафедра (departments.department_id)",
        },
    },
    "specialties": {
        "title": "Направления подготовки",
        "description": "Направления подготовки (специальности).",
        "primary_key": ["specialty_id"],
        "foreign_keys": [
            {
                "column": "faculty_id",
                "references_table": "faculties",
                "references_column": "faculty_id",
            },
        ],
        "columns": {
            "specialty_id": "Идентификатор направления",
            "code": "Код направления (например, 09.03.01)",
            "title": "Название направления",
            "faculty_id": "Факультет (faculties.faculty_id)",
            "total_semesters": "Общее число семестров",
        },
    },
    "student_statuses": {
        "title": "Статусы студентов",
        "description": "Справочник статусов студентов.",
        "primary_key": ["status_id"],
        "foreign_keys": [],
        "columns": {
            "status_id": "Идентификатор статуса",
            "title": "Название статуса (например, «обучается», «отчислен»)",
        },
    },
    "groups": {
        "title": "Учебные группы",
        "description": "Учебные группы.",
        "primary_key": ["group_id"],
        "foreign_keys": [
            {
                "column": "specialty_id",
                "references_table": "specialties",
                "references_column": "specialty_id",
            },
        ],
        "columns": {
            "group_id": "Идентификатор группы",
            "title": "Название группы",
            "specialty_id": "Направление (specialties.specialty_id)",
            "admission_year": "Год набора",
        },
    },
    "students": {
        "title": "Профили студентов",
        "description": (
            "Профили студентов. Поля name, surname, patronymic, passport — "
            "персональные данные: доступны только администрации и не должны "
            "попадать в ответы."
        ),
        "primary_key": ["student_id"],
        "foreign_keys": [
            {
                "column": "specialty_id",
                "references_table": "specialties",
                "references_column": "specialty_id",
            },
            {
                "column": "group_id",
                "references_table": "groups",
                "references_column": "group_id",
            },
            {
                "column": "status_id",
                "references_table": "student_statuses",
                "references_column": "status_id",
            },
        ],
        "columns": {
            "student_id": "Идентификатор студента",
            "name": "Имя (персональные данные)",
            "surname": "Фамилия (персональные данные)",
            "patronymic": "Отчество (персональные данные)",
            "passport": "Номер паспорта (персональные данные)",
            "specialty_id": "Направление (specialties.specialty_id)",
            "group_id": "Группа (groups.group_id)",
            "admission_year": "Год поступления",
            "status_id": "Статус (student_statuses.status_id)",
        },
    },
    "courses": {
        "title": "Учебные дисциплины",
        "description": "Учебные дисциплины.",
        "primary_key": ["course_id"],
        "foreign_keys": [
            {
                "column": "department_id",
                "references_table": "departments",
                "references_column": "department_id",
            },
        ],
        "columns": {
            "course_id": "Идентификатор дисциплины",
            "title": "Название дисциплины",
            "department_id": "Кафедра (departments.department_id)",
            "semester": "Номер семестра (1-8)",
            "lecture_hours": "Лекционные часы",
        },
    },
    "course_instructors": {
        "title": "Назначение преподавателей на курсы",
        "description": "Связь преподавателей и дисциплин.",
        "primary_key": ["course_id", "staff_id"],
        "foreign_keys": [
            {
                "column": "course_id",
                "references_table": "courses",
                "references_column": "course_id",
            },
            {
                "column": "staff_id",
                "references_table": "staff",
                "references_column": "staff_id",
            },
        ],
        "columns": {
            "course_id": "Дисциплина (courses.course_id)",
            "staff_id": "Преподаватель (staff.staff_id)",
        },
    },
    "academic_records": {
        "title": "Успеваемость студентов",
        "description": "Оценки студентов по дисциплинам.",
        "primary_key": ["record_id"],
        "foreign_keys": [
            {
                "column": "student_id",
                "references_table": "students",
                "references_column": "student_id",
            },
            {
                "column": "course_id",
                "references_table": "courses",
                "references_column": "course_id",
            },
        ],
        "columns": {
            "record_id": "Идентификатор записи",
            "student_id": "Студент (students.student_id)",
            "course_id": "Дисциплина (courses.course_id)",
            "grade": "Оценка от 0 до 5 (NULL — не аттестован)",
            "has_debt": "Есть академическая задолженность",
            "semester": "Номер семестра",
        },
    },
    "rooms": {
        "title": "Аудитории",
        "description": "Аудиторный фонд.",
        "primary_key": ["room_id"],
        "foreign_keys": [],
        "columns": {
            "room_id": "Идентификатор аудитории",
            "building": "Корпус",
            "number": "Номер аудитории",
            "capacity": "Вместимость",
        },
    },
    "schedule_slots": {
        "title": "Расписание занятий",
        "description": "Расписание занятий.",
        "primary_key": ["slot_id"],
        "foreign_keys": [
            {
                "column": "course_id",
                "references_table": "courses",
                "references_column": "course_id",
            },
            {
                "column": "group_id",
                "references_table": "groups",
                "references_column": "group_id",
            },
            {
                "column": "room_id",
                "references_table": "rooms",
                "references_column": "room_id",
            },
        ],
        "columns": {
            "slot_id": "Идентификатор слота",
            "course_id": "Дисциплина (courses.course_id)",
            "group_id": "Группа (groups.group_id)",
            "room_id": "Аудитория (rooms.room_id)",
            "weekday": "День недели (1-7)",
            "period": "Номер пары (1-8)",
        },
    },
    "admission_plans": {
        "title": "Контрольные цифры приёма",
        "description": "Плановые показатели приёма по годам.",
        "primary_key": ["plan_id"],
        "foreign_keys": [
            {
                "column": "specialty_id",
                "references_table": "specialties",
                "references_column": "specialty_id",
            },
        ],
        "columns": {
            "plan_id": "Идентификатор плана",
            "year": "Год приёма",
            "specialty_id": "Направление (specialties.specialty_id)",
            "budget_places": "Бюджетные места",
            "paid_places": "Платные места",
            "application_deadline": "Дата окончания приёма документов",
        },
    },
    "admission_stats": {
        "title": "Статистика приёма",
        "description": "Фактическая статистика приёма по годам.",
        "primary_key": ["stat_id"],
        "foreign_keys": [
            {
                "column": "specialty_id",
                "references_table": "specialties",
                "references_column": "specialty_id",
            },
        ],
        "columns": {
            "stat_id": "Идентификатор записи",
            "year": "Год приёма",
            "specialty_id": "Направление (specialties.specialty_id)",
            "applications": "Число заявлений",
            "enrolled": "Число зачисленных",
            "passing_score": "Проходной балл",
            "avg_score": "Средний балл",
        },
    },
}

# Каталог читаем через пул роли: для app_ro PII-колонки и служебные таблицы
# не показываются (нет привилегий), для app_admin — показываются все.
_CATALOG_SQL = """
    SELECT c.table_name,
           c.column_name,
           c.data_type,
           c.is_nullable
      FROM information_schema.columns c
     WHERE c.table_schema = 'public'
       AND c.table_name != ALL($1::text[])
     ORDER BY c.table_name, c.ordinal_position
"""


class SchemaBuilder:
    """Формирует маскированное описание схемы под роль."""

    def __init__(self, pools: Pools) -> None:
        self._pools = pools

    async def describe(self, role: str) -> list[dict[str, object]]:
        """Описание таблиц (с колонками) для заданной роли.

        PII-колонки студентов для ролей без прав на них отсутствуют в каталоге
        (их физически не видит app_ro) и не попадают в результат.
        """
        pool = await self._pools.pool_for_role(role)
        rows = await pool.fetch(_CATALOG_SQL, sorted(EXCLUDED_TABLES))

        grouped: dict[str, list[asyncpg.Record]] = defaultdict(list)
        for row in rows:
            grouped[row["table_name"]].append(row)

        sensitive = SENSITIVE_COLUMNS
        tables: list[dict[str, object]] = []
        for table_name in sorted(grouped):
            meta = TABLE_META.get(table_name)
            columns_meta = meta["columns"] if meta else {}
            table_cols = [
                {
                    "name": row["column_name"],
                    "type": row["data_type"],
                    "nullable": row["is_nullable"] == "YES",
                    "description": columns_meta.get(row["column_name"]),
                    "sensitive": row["column_name"] in sensitive.get(table_name, set()),
                }
                for row in grouped[table_name]
            ]
            tables.append(
                {
                    "name": table_name,
                    "title": meta["title"] if meta else None,
                    "description": meta["description"] if meta else None,
                    "primary_key": meta["primary_key"] if meta else [],
                    "foreign_keys": meta["foreign_keys"] if meta else [],
                    "columns": table_cols,
                }
            )
        return tables
