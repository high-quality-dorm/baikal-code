"""Описание схемы БД для LLM, маскированное под пользователя.

Схема читается из живого каталога PostgreSQL (information_schema.columns)
через рабочую роль app_ro. Маскирование на уровне описания:

- гость (identity is None): таблицы `students`/`marks` (и служебные
  `users`/`query_log`) в описание не попадают — персональных данных нет вовсе;
- любой аутентифицированный пользователь (есть student_id и/или staff_id):
  видны все доменные таблицы, а скоуп строк ограничивает RLS (кто видит строку
  студента, тот видит и её PII-поля);
- публичные агрегатные вью `v_*` (04_views.sql) видны **всем** (включая гостя):
  это только численность студентов, без персональных данных.

К каталогу добавляются русские описания таблиц и колонок, пометка PII-колонок
(как метаданные для промпта), а также статические PK/FK из TABLE_META
(для генерации JOIN).
"""

from __future__ import annotations

from collections import defaultdict
from typing import TypedDict

import asyncpg

from db.access import Pools
from db.models import ColumnInfo, ForeignKey, Identity, TableInfo

# Служебные таблицы, которые никогда не попадают в описание схемы для LLM
EXCLUDED_TABLES = frozenset({"users", "query_log"})

# Персональные данные студентов: помечаются как sensitive (для промпта), но
# видимость строк задаёт RLS — аутентифицированные роли видят PII тех строк,
# которые им открыты.
SENSITIVE_COLUMNS = {
    "students": frozenset({"name", "surname", "patronymic"}),
}


class _ForeignKeyMeta(TypedDict):
    """Внешний ключ в статическом описании таблицы."""

    column: str
    references_table: str
    references_column: str


class _TableMeta(TypedDict):
    """Статическое описание таблицы: заголовок, колонки и ключи."""

    title: str
    description: str
    primary_key: list[str]
    foreign_keys: list[_ForeignKeyMeta]
    columns: dict[str, str]


# Русские описания таблиц и колонок (для генерации SQL и безопасности).
# PK/FK хранятся здесь статически, а не читаются из каталога: описание и так
# хардкодится, а information_schema не отдаёт constraints без привилегий.
TABLE_META: dict[str, _TableMeta] = {
    "buildings": {
        "title": "Здания",
        "description": "Корпуса университета.",
        "primary_key": ["id"],
        "foreign_keys": [],
        "columns": {
            "id": "Идентификатор здания",
            "title": "Название корпуса",
        },
    },
    "faculties": {
        "title": "Факультеты",
        "description": "Факультеты университета.",
        "primary_key": ["id"],
        "foreign_keys": [
            {
                "column": "dean_id",
                "references_table": "staff",
                "references_column": "id",
            }
        ],
        "columns": {
            "id": "Идентификатор факультета",
            "title": "Название факультета",
            "dean_id": "Декан (staff.id)",
        },
    },
    "departments": {
        "title": "Кафедры",
        "description": "Кафедры, входящие в состав факультетов.",
        "primary_key": ["id"],
        "foreign_keys": [
            {
                "column": "faculty_id",
                "references_table": "faculties",
                "references_column": "id",
            },
            {
                "column": "head_id",
                "references_table": "staff",
                "references_column": "id",
            },
        ],
        "columns": {
            "id": "Идентификатор кафедры",
            "title": "Название кафедры",
            "faculty_id": "Факультет (faculties.id)",
            "head_id": "Заведующий кафедрой (staff.id)",
        },
    },
    "specializations": {
        "title": "Направления подготовки",
        "description": "Направления подготовки (специальности).",
        "primary_key": ["id"],
        "foreign_keys": [
            {
                "column": "faculty_id",
                "references_table": "faculties",
                "references_column": "id",
            }
        ],
        "columns": {
            "id": "Идентификатор направления",
            "faculty_id": "Факультет (faculties.id)",
            "code": "Код направления (например, 09.03.01)",
            "title": "Название направления",
        },
    },
    "groups": {
        "title": "Учебные группы",
        "description": "Учебные группы.",
        "primary_key": ["id"],
        "foreign_keys": [
            {
                "column": "specialization_id",
                "references_table": "specializations",
                "references_column": "id",
            }
        ],
        "columns": {
            "id": "Идентификатор группы",
            "specialization_id": "Направление (specializations.id)",
            "title": "Название группы",
            "admission_year": "Год набора",
        },
    },
    "student_statuses": {
        "title": "Статусы студентов",
        "description": "Справочник статусов студентов.",
        "primary_key": ["id"],
        "foreign_keys": [],
        "columns": {
            "id": "Идентификатор статуса",
            "title": "Название статуса (например, «обучается», «отчислен»)",
            "is_studying": "Учится сейчас (да/нет)",
        },
    },
    "students": {
        "title": "Профили студентов",
        "description": (
            "Профили студентов. Поля name, surname, patronymic — персональные "
            "данные: видимы только тем, кому RLS открывает строку студента."
        ),
        "primary_key": ["id"],
        "foreign_keys": [
            {
                "column": "group_id",
                "references_table": "groups",
                "references_column": "id",
            },
            {
                "column": "status_id",
                "references_table": "student_statuses",
                "references_column": "id",
            },
        ],
        "columns": {
            "id": "Идентификатор студента",
            "group_id": "Группа (groups.id)",
            "status_id": "Статус (student_statuses.id)",
            "admission_year": "Год поступления",
            "name": "Имя (персональные данные)",
            "surname": "Фамилия (персональные данные)",
            "patronymic": "Отчество (персональные данные)",
        },
    },
    "positions": {
        "title": "Должности персонала",
        "description": "Справочник должностей сотрудников.",
        "primary_key": ["id"],
        "foreign_keys": [],
        "columns": {
            "id": "Идентификатор должности",
            "title": "Название должности (teacher/head/dean/admin)",
        },
    },
    "staff": {
        "title": "Сотрудники и преподаватели",
        "description": "Сотрудники и преподаватели университета. ФИО публично.",
        "primary_key": ["id"],
        "foreign_keys": [
            {
                "column": "faculty_id",
                "references_table": "faculties",
                "references_column": "id",
            },
            {
                "column": "department_id",
                "references_table": "departments",
                "references_column": "id",
            },
            {
                "column": "position_id",
                "references_table": "positions",
                "references_column": "id",
            },
        ],
        "columns": {
            "id": "Идентификатор сотрудника",
            "faculty_id": "Факультет (faculties.id)",
            "department_id": "Кафедра (departments.id)",
            "position_id": "Должность (positions.id)",
            "name": "Имя",
            "surname": "Фамилия",
            "patronymic": "Отчество",
        },
    },
    "subjects": {
        "title": "Дисциплины",
        "description": "Учебные дисциплины.",
        "primary_key": ["id"],
        "foreign_keys": [
            {
                "column": "department_id",
                "references_table": "departments",
                "references_column": "id",
            }
        ],
        "columns": {
            "id": "Идентификатор дисциплины",
            "title": "Название дисциплины",
            "department_id": "Кафедра (departments.id)",
        },
    },
    "terms": {
        "title": "Семестры",
        "description": "Учебные годы и семестры.",
        "primary_key": ["id"],
        "foreign_keys": [],
        "columns": {
            "id": "Идентификатор семестра",
            "year": "Учебный год",
            "semester": "Номер семестра (1-2)",
            "date_start": "Дата начала",
            "date_end": "Дата окончания",
        },
    },
    "classrooms": {
        "title": "Аудитории",
        "description": "Аудиторный фонд.",
        "primary_key": ["id"],
        "foreign_keys": [
            {
                "column": "building_id",
                "references_table": "buildings",
                "references_column": "id",
            }
        ],
        "columns": {
            "id": "Идентификатор аудитории",
            "building_id": "Здание (buildings.id)",
            "number": "Номер аудитории",
            "capacity": "Вместимость",
        },
    },
    "lessons": {
        "title": "Занятия",
        "description": "Расписание занятий.",
        "primary_key": ["id"],
        "foreign_keys": [
            {
                "column": "subject_id",
                "references_table": "subjects",
                "references_column": "id",
            },
            {
                "column": "classroom_id",
                "references_table": "classrooms",
                "references_column": "id",
            },
            {
                "column": "teacher_id",
                "references_table": "staff",
                "references_column": "id",
            },
            {
                "column": "term_id",
                "references_table": "terms",
                "references_column": "id",
            },
        ],
        "columns": {
            "id": "Идентификатор занятия",
            "subject_id": "Дисциплина (subjects.id)",
            "classroom_id": "Аудитория (classrooms.id)",
            "teacher_id": "Преподаватель (staff.id)",
            "term_id": "Семестр (terms.id)",
            "weekday": "День недели (1-7)",
            "period": "Номер пары (1-8)",
        },
    },
    "lesson_group": {
        "title": "Занятия и группы",
        "description": "Связь занятий и учебных групп (many-to-many).",
        "primary_key": ["lesson_id", "group_id"],
        "foreign_keys": [
            {
                "column": "lesson_id",
                "references_table": "lessons",
                "references_column": "id",
            },
            {
                "column": "group_id",
                "references_table": "groups",
                "references_column": "id",
            },
        ],
        "columns": {
            "lesson_id": "Занятие (lessons.id)",
            "group_id": "Группа (groups.id)",
        },
    },
    "marks": {
        "title": "Успеваемость студентов",
        "description": "Оценки студентов по дисциплинам.",
        "primary_key": ["id"],
        "foreign_keys": [
            {
                "column": "student_id",
                "references_table": "students",
                "references_column": "id",
            },
            {
                "column": "subject_id",
                "references_table": "subjects",
                "references_column": "id",
            },
            {
                "column": "term_id",
                "references_table": "terms",
                "references_column": "id",
            },
        ],
        "columns": {
            "id": "Идентификатор записи",
            "student_id": "Студент (students.id)",
            "subject_id": "Дисциплина (subjects.id)",
            "term_id": "Семестр (terms.id)",
            "grade": "Оценка от 0 до 5 (NULL — не аттестован)",
            "has_debt": "Есть академическая задолженность",
        },
    },
    "admission_campaigns": {
        "title": "Приёмные кампании",
        "description": "Приёмные кампании по годам.",
        "primary_key": ["id"],
        "foreign_keys": [],
        "columns": {
            "id": "Идентификатор кампании",
            "year": "Год приёма",
        },
    },
    "admission_committees": {
        "title": "Приёмные комиссии",
        "description": "Приёмные комиссии по факультетам на кампанию.",
        "primary_key": ["id"],
        "foreign_keys": [
            {
                "column": "campaign_id",
                "references_table": "admission_campaigns",
                "references_column": "id",
            },
            {
                "column": "faculty_id",
                "references_table": "faculties",
                "references_column": "id",
            },
            {
                "column": "head_staff_id",
                "references_table": "staff",
                "references_column": "id",
            },
        ],
        "columns": {
            "id": "Идентификатор комиссии",
            "campaign_id": "Кампания (admission_campaigns.id)",
            "faculty_id": "Факультет (faculties.id)",
            "head_staff_id": "Председатель (staff.id)",
            "location": "Место приёма",
            "phone": "Телефон",
            "email": "Email",
            "working_hours": "Часы работы",
        },
    },
    "admission_committee_members": {
        "title": "Состав приёмных комиссий",
        "description": "Сотрудники в составе приёмных комиссий.",
        "primary_key": ["committee_id", "staff_id"],
        "foreign_keys": [
            {
                "column": "committee_id",
                "references_table": "admission_committees",
                "references_column": "id",
            },
            {
                "column": "staff_id",
                "references_table": "staff",
                "references_column": "id",
            },
        ],
        "columns": {
            "committee_id": "Комиссия (admission_committees.id)",
            "staff_id": "Сотрудник (staff.id)",
        },
    },
    "admission_plans": {
        "title": "Контрольные цифры приёма",
        "description": "Плановые показатели приёма по направлениям.",
        "primary_key": ["id"],
        "foreign_keys": [
            {
                "column": "campaign_id",
                "references_table": "admission_campaigns",
                "references_column": "id",
            },
            {
                "column": "specialization_id",
                "references_table": "specializations",
                "references_column": "id",
            },
        ],
        "columns": {
            "id": "Идентификатор плана",
            "campaign_id": "Кампания (admission_campaigns.id)",
            "specialization_id": "Направление (specializations.id)",
            "budget_places": "Бюджетные места",
            "paid_places": "Платные места",
            "application_deadline": "Дата окончания приёма документов",
        },
    },
    "admission_stats": {
        "title": "Статистика приёма",
        "description": "Фактическая статистика приёма по направлениям.",
        "primary_key": ["id"],
        "foreign_keys": [
            {
                "column": "campaign_id",
                "references_table": "admission_campaigns",
                "references_column": "id",
            },
            {
                "column": "specialization_id",
                "references_table": "specializations",
                "references_column": "id",
            },
        ],
        "columns": {
            "id": "Идентификатор записи",
            "campaign_id": "Кампания (admission_campaigns.id)",
            "specialization_id": "Направление (specializations.id)",
            "applications": "Число заявлений",
            "enrolled": "Число зачисленных",
            "passing_score": "Проходной балл",
            "avg_score": "Средний балл",
        },
    },
    # Публичные агрегаты по студентам (вью db/04_views.sql): только численность,
    # без персональных данных. Видны всем пользователям, включая гостя. PK —
    # группирующая колонка (у total пусто), FK нет: вью самодостаточны, чтобы
    # LLM не плодил лишние JOIN'ы.
    "v_students_total": {
        "title": "Всего студентов (публичная статистика)",
        "description": (
            "Общее число студентов. Публичная агрегатная статистика без "
            "персональных данных; доступна всем, включая гостя."
        ),
        "primary_key": [],
        "foreign_keys": [],
        "columns": {
            "students": "Всего студентов",
        },
    },
    "v_students_by_faculty": {
        "title": "Студенты по факультетам (публичная статистика)",
        "description": (
            "Численность студентов по факультетам. Публичная агрегатная "
            "статистика без персональных данных."
        ),
        "primary_key": ["faculty_id"],
        "foreign_keys": [],
        "columns": {
            "faculty_id": "Факультет (faculties.id)",
            "faculty_title": "Название факультета",
            "students": "Число студентов",
        },
    },
    "v_students_by_specialization": {
        "title": "Студенты по направлениям (публичная статистика)",
        "description": (
            "Численность студентов по направлениям подготовки. Публичная "
            "агрегатная статистика без персональных данных."
        ),
        "primary_key": ["specialization_id"],
        "foreign_keys": [],
        "columns": {
            "specialization_id": "Направление (specializations.id)",
            "code": "Код направления (например, 09.03.01)",
            "specialization_title": "Название направления",
            "faculty_title": "Факультет",
            "students": "Число студентов",
        },
    },
    "v_students_by_group": {
        "title": "Студенты по группам (публичная статистика)",
        "description": (
            "Численность студентов по учебным группам. Публичная агрегатная "
            "статистика без персональных данных."
        ),
        "primary_key": ["group_id"],
        "foreign_keys": [],
        "columns": {
            "group_id": "Группа (groups.id)",
            "group_title": "Название группы",
            "specialization_title": "Направление подготовки",
            "admission_year": "Год набора",
            "students": "Число студентов",
        },
    },
    "v_students_by_status": {
        "title": "Студенты по статусам (публичная статистика)",
        "description": (
            "Численность студентов по статусам (обучается, отчислен, "
            "академический отпуск, выпускник). Публичная агрегатная статистика "
            "без персональных данных."
        ),
        "primary_key": ["status_id"],
        "foreign_keys": [],
        "columns": {
            "status_id": "Статус (student_statuses.id)",
            "status_title": "Название статуса",
            "is_studying": "Учится сейчас (да/нет)",
            "students": "Число студентов",
        },
    },
    "v_students_by_admission_year": {
        "title": "Студенты по году поступления (публичная статистика)",
        "description": (
            "Численность студентов по году поступления. Публичная агрегатная "
            "статистика без персональных данных."
        ),
        "primary_key": ["admission_year"],
        "foreign_keys": [],
        "columns": {
            "admission_year": "Год поступления",
            "students": "Число студентов",
        },
    },
    "v_students_expelled": {
        "title": "Отчисленные студенты (публичная статистика)",
        "description": (
            "Статистика отчислений: численность отчисленных по году поступления "
            "и факультету. Без персональных данных."
        ),
        "primary_key": ["admission_year", "faculty_id"],
        "foreign_keys": [],
        "columns": {
            "admission_year": "Год поступления",
            "faculty_id": "Факультет (faculties.id)",
            "faculty_title": "Название факультета",
            "students": "Число отчисленных",
        },
    },
}

# Каталог читается через пул app_ro: колоночных грантов в v2 нет, поэтому
# маскирование выполняется на уровне описания (гость vs аутентифицированный).
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
    """Формирует маскированное описание схемы под пользователя."""

    def __init__(self, pools: Pools) -> None:
        self._pools = pools

    async def describe(self, identity: Identity | None) -> list[TableInfo]:
        """Описание таблиц (с колонками) для пользователя.

        Гость (identity None) не видит students/marks; аутентифицированный
        пользователь видит все доменные таблицы (скоуп строк задаёт RLS).
        """
        excluded = set(EXCLUDED_TABLES)
        if identity is None:
            excluded |= {"students", "marks"}

        pool = await self._pools.ro()
        rows = await pool.fetch(_CATALOG_SQL, sorted(excluded))

        grouped: dict[str, list[asyncpg.Record]] = defaultdict(list)
        for row in rows:
            grouped[row["table_name"]].append(row)

        sensitive = SENSITIVE_COLUMNS
        tables: list[TableInfo] = []
        for table_name in sorted(grouped):
            meta = TABLE_META.get(table_name, {})
            columns_meta = meta.get("columns", {})
            table_cols = [
                ColumnInfo(
                    name=row["column_name"],
                    type=row["data_type"],
                    nullable=row["is_nullable"] == "YES",
                    description=columns_meta.get(row["column_name"]),
                    sensitive=row["column_name"] in sensitive.get(table_name, set()),
                )
                for row in grouped[table_name]
            ]
            tables.append(
                TableInfo(
                    name=table_name,
                    title=meta.get("title"),
                    description=meta.get("description"),
                    primary_key=list(meta.get("primary_key", [])),
                    foreign_keys=[
                        ForeignKey(**fk) for fk in meta.get("foreign_keys", [])
                    ],
                    columns=table_cols,
                )
            )
        return tables
