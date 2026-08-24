"""Описание схемы БД для LLM, маскированное под роль.

Схема читается из живого каталога PostgreSQL (information_schema.columns)
через пул соединений той роли, для которой формируется описание:

- для app_ro (applicant/student/teacher) каталог физически не показывает
  PII-колонки студентов и служебные таблицы (нет привилегий) — маскирование
  происходит на уровне БД;
- для app_admin (admin) виден полный набор колонок, а чувствительные поля
  помечаются флагом `sensitive`, чтобы LLM не выводил их в ответах.

К каталогу добавляются русские описания таблиц и колонок (для генерации
корректного SQL) и пометка PII-колонок.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TypedDict

import asyncpg

from db_mcp.access import Pools


class _TableMeta(TypedDict):
    """Русские описания таблицы: заголовок, описание и описания колонок."""

    title: str
    description: str
    columns: dict[str, str]


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
        "columns": {
            "faculty_id": "Идентификатор факультета",
            "title": "Название факультета",
            "dean_id": "Декан (staff.staff_id)",
        },
    },
    "departments": {
        "title": "Кафедры",
        "description": "Кафедры, входящие в состав факультетов.",
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
        "columns": {
            "id": "Идентификатор роли",
            "title": "Название роли",
        },
    },
    "staff": {
        "title": "Сотрудники и преподаватели",
        "description": "Сотрудники и преподаватели университета. ФИО выводимо.",
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
        "columns": {
            "status_id": "Идентификатор статуса",
            "title": "Название статуса (например, «обучается», «отчислен»)",
        },
    },
    "groups": {
        "title": "Учебные группы",
        "description": "Учебные группы.",
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
        "columns": {
            "course_id": "Дисциплина (courses.course_id)",
            "staff_id": "Преподаватель (staff.staff_id)",
        },
    },
    "academic_records": {
        "title": "Успеваемость студентов",
        "description": "Оценки студентов по дисциплинам.",
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
                    "columns": table_cols,
                }
            )
        return tables
