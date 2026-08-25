"""Генератор синтетических данных для базы университета.

Идемпотентный: перед наполнением делает TRUNCATE ... RESTART IDENTITY CASCADE
всех таблиц. Использует фиксированный seed для детерминированности.

Подключается как app_owner (владелец схемы) из .env (DATABASE_URL_OWNER).

Точка входа: `make seed` или `uv run python scripts/seed.py`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date

import asyncpg
from faker import Faker
from pydantic_settings import BaseSettings, SettingsConfigDict

from db_mcp.roles import BusinessRole

# Опорная дата «текущего семестра»: осенний семестр 2026/27 учебного года
# (сентябрь 2026). Семестры отсчитываются от неё.
REFERENCE_YEAR = 2026
REFERENCE_SEMESTER = 1  # 1 = осень, 2 = весна


class Settings(BaseSettings):
    """Настройки подключения для сида."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url_owner: str = "postgresql://app_owner:owner@localhost:5432/university"


settings = Settings()

# Временные диапазоны набора: студенты приходят с 2019 по 2026 год.
ADMISSION_YEARS = list(range(2019, 2027))

# Глобальный пул дисциплин (учебный план по факультетам), каждый факультет
# имеет типовые курсы на каждый семестр (1-8).
CURRICULUM = {
    "ИВТ и информатика": {
        1: [
            "Основы программирования",
            "Дискретная математика",
            "Введение в специальность",
            "Математический анализ",
        ],
        2: [
            "Алгоритмы и структуры данных",
            "Линейная алгебра",
            "Дискретная математика",
        ],
        3: [
            "Объектно-ориентированное программирование",
            "Теория вероятностей",
            "Компьютерные сети",
        ],
        4: ["Базы данных", "Операционные системы", "Теория вероятностей"],
        5: [
            "Теория автоматического управления",
            "Веб-разработка",
            "Методы оптимизации",
        ],
        6: ["Машинное обучение", "Распределённые системы", "Программная инженерия"],
        7: ["Искусственный интеллект", "Проектирование ИС", "Кибербезопасность"],
        8: ["Выпускная квалификационная работа", "Управление проектами", "Big Data"],
    },
    "Экономика и управление": {
        1: ["Микроэкономика", "Математический анализ", "Введение в экономику"],
        2: ["Макроэкономика", "Статистика", "Экономическая теория"],
        3: ["Финансы", "Бухгалтерский учёт", "Эконометрика"],
        4: ["Менеджмент", "Экономика предприятия", "Налоги"],
        5: ["Маркетинг", "Инвестиции", "Анализ хозяйственной деятельности"],
        6: [
            "Стратегический менеджмент",
            "Управление персоналом",
            "Корпоративные финансы",
        ],
        7: ["Логистика", "Бизнес-планирование", "Экономическая безопасность"],
        8: [
            "Выпускная квалификационная работа",
            "Антикризисное управление",
            "Международная экономика",
        ],
    },
    "Гуманитарные науки": {
        1: ["История", "Философия", "Культурология", "Русский язык"],
        2: ["Социология", "Психология", "Философия", "Иностранный язык"],
        3: ["Политология", "Педагогика", "История мировой культуры"],
        4: ["Социальная работа", "Психология личности", "Этика"],
        5: ["Методы социологических исследований", "История искусств", "Риторика"],
        6: ["Управление социальными проектами", "Социальная психология", "Логика"],
        7: [
            "Современные концепции гуманитарного знания",
            "Когнитивная психология",
            "Социология культуры",
        ],
        8: [
            "Выпускная квалификационная работа",
            "Философия науки",
            "Кросскультурные коммуникации",
        ],
    },
    "Естественные науки": {
        1: ["Математический анализ", "Физика", "Аналитическая химия"],
        2: ["Линейная алгебра", "Физика", "Общая химия"],
        3: ["Дифференциальные уравнения", "Физическая химия", "Теория поля"],
        4: ["Методы математической физики", "Органическая химия", "Термодинамика"],
        5: ["Квантовая механика", "Спектроскопия", "Численные методы"],
        6: [
            "Статистическая физика",
            "Химическая кинетика",
            "Математическое моделирование",
        ],
        7: ["Физика конденсированного состояния", "Биохимия", "Вычислительная физика"],
        8: [
            "Выпускная квалификационная работа",
            "Современные проблемы физики",
            "Научный семинар",
        ],
    },
    "Инженерия и технологии": {
        1: [
            "Начертательная геометрия",
            "Инженерная графика",
            "Материаловедение",
            "Физика",
        ],
        2: ["Теоретическая механика", "Сопротивление материалов", "Электротехника"],
        3: ["Детали машин", "Технология машиностроения", "Гидравлика"],
        4: ["Метрология", "Теплотехника", "Автоматизация производства"],
        5: ["Робототехника", "CAD/CAM системы", "Электроника"],
        6: ["Мехатроника", "Управление техническими системами", "Надёжность машин"],
        7: [
            "Проектирование технологических процессов",
            "Инженерный эксперимент",
            "САПР",
        ],
        8: [
            "Выпускная квалификационная работа",
            "Инновационные технологии",
            "Инженерная экономика",
        ],
    },
}

FACULTIES = [
    ("ИВТ и информатика", "Факультет информационных технологий"),
    ("Экономика и управление", "Экономический факультет"),
    ("Гуманитарные науки", "Гуманитарный факультет"),
    ("Естественные науки", "Факультет естественных наук"),
    ("Инженерия и технологии", "Инженерно-технический факультет"),
]

# Кодовые префиксы специальностей по факультетам
SPECIALTY_CODES = {
    "ИВТ и информатика": [
        "09.03.01",
        "09.03.02",
        "09.03.03",
        "02.03.02",
        "10.03.01",
        "01.03.02",
    ],
    "Экономика и управление": [
        "38.03.01",
        "38.03.02",
        "38.03.05",
        "38.03.06",
        "43.03.03",
    ],
    "Гуманитарные науки": ["39.03.01", "37.03.01", "42.03.01", "44.03.05", "46.03.01"],
    "Естественные науки": ["03.03.02", "04.03.01", "01.03.01", "05.03.02", "06.03.01"],
    "Инженерия и технологии": [
        "15.03.01",
        "15.03.04",
        "15.03.06",
        "13.03.02",
        "27.03.04",
    ],
}

# Специальные названия (для кодов, где нужно человекочитаемое название)
SPECIALTY_TITLES = {
    "09.03.01": "Информатика и вычислительная техника",
    "09.03.02": "Информационные системы и технологии",
    "09.03.03": "Прикладная информатика",
    "02.03.02": "Фундаментальная информатика и информационные технологии",
    "10.03.01": "Информационная безопасность",
    "01.03.02": "Прикладная математика и информатика",
    "38.03.01": "Экономика",
    "38.03.02": "Менеджмент",
    "38.03.05": "Бизнес-информатика",
    "38.03.06": "Торговое дело",
    "43.03.03": "Гостиничное дело",
    "39.03.01": "Социология",
    "37.03.01": "Психология",
    "42.03.01": "Реклама и связи с общественностью",
    "44.03.05": "Педагогическое образование",
    "46.03.01": "История",
    "03.03.02": "Физика",
    "04.03.01": "Химия",
    "01.03.01": "Математика",
    "05.03.02": "География",
    "06.03.01": "Биология",
    "15.03.01": "Машиностроение",
    "15.03.04": "Автоматизация технологических процессов",
    "15.03.06": "Мехатроника и робототехника",
    "13.03.02": "Электроэнергетика и электротехника",
    "27.03.04": "Управление в технических системах",
}

STAFF_ROLES = ["Ректор", "Декан", "Зав. кафедрой", "Преподаватель", "Сотрудник"]


@dataclass
class SeedContext:
    """Накопленные id вставленных сущностей (для связывания FK)."""

    conn: asyncpg.Connection
    faker: Faker = field(default_factory=lambda: Faker("ru_RU"))
    random: random.Random = field(default_factory=lambda: random.Random(42))

    faculty_ids: dict[str, int] = field(default_factory=dict)
    department_ids: list[int] = field(default_factory=list)
    dept_by_faculty: dict[str, list[int]] = field(default_factory=dict)
    staff_ids: list[int] = field(default_factory=list)
    staff_teachers: list[int] = field(default_factory=list)
    specialty_ids: list[int] = field(default_factory=list)
    specialty_by_code: dict[str, int] = field(default_factory=dict)
    group_ids: list[int] = field(default_factory=list)
    student_ids: list[int] = field(default_factory=list)
    course_ids: list[int] = field(default_factory=list)
    course_by_faculty_semester: dict[tuple[str, int], list[int]] = field(
        default_factory=dict
    )
    room_ids: list[int] = field(default_factory=list)
    status_ids: dict[str, int] = field(default_factory=dict)


async def seed_faculties_departments(ctx: SeedContext) -> None:
    """Создаёт факультеты, кафедры и роли сотрудников."""
    for role in STAFF_ROLES:
        await ctx.conn.execute("INSERT INTO roles (title) VALUES ($1)", role)

    for name, _title in FACULTIES:
        fid = await ctx.conn.fetchval(
            "INSERT INTO faculties (title, dean_id) VALUES ($1, NULL) RETURNING faculty_id",
            name,
        )
        ctx.faculty_ids[name] = fid
        # 2-3 кафедры на факультет
        ctx.dept_by_faculty[name] = []
        for i in range(ctx.random.randint(2, 3)):
            dept_id = await ctx.conn.fetchval(
                "INSERT INTO departments (title, faculty_id, head_id) VALUES ($1, $2, NULL) RETURNING department_id",
                f"{name} — кафедра №{i + 1}",
                fid,
            )
            ctx.department_ids.append(dept_id)
            ctx.dept_by_faculty[name].append(dept_id)


async def seed_staff(ctx: SeedContext) -> None:
    """Создаёт сотрудников и преподавателей."""
    # Получаем id ролей
    role_ids: dict[str, int] = {}
    for row in await ctx.conn.fetch("SELECT id, title FROM roles"):
        role_ids[row["title"]] = row["id"]

    # Ректор (1)
    rector_id = await ctx.conn.fetchval(
        "INSERT INTO staff (full_name, role_id, department_id) VALUES ($1, $2, NULL) RETURNING staff_id",
        _full_name(ctx),
        role_ids["Ректор"],
    )
    ctx.staff_ids.append(rector_id)

    # Деканы (по одному на факультет) + зав. кафедрами + преподаватели + сотрудники
    for fac_name, fid in ctx.faculty_ids.items():
        dean_id = await ctx.conn.fetchval(
            "INSERT INTO staff (full_name, role_id, department_id) VALUES ($1, $2, $3) RETURNING staff_id",
            _full_name(ctx),
            role_ids["Декан"],
            None,
        )
        ctx.staff_ids.append(dean_id)
        await ctx.conn.execute(
            "UPDATE faculties SET dean_id = $1 WHERE faculty_id = $2", dean_id, fid
        )

        for dept_id in ctx.dept_by_faculty[fac_name]:
            head_id = await ctx.conn.fetchval(
                "INSERT INTO staff (full_name, role_id, department_id) VALUES ($1, $2, $3) RETURNING staff_id",
                _full_name(ctx),
                role_ids["Зав. кафедрой"],
                dept_id,
            )
            ctx.staff_ids.append(head_id)
            await ctx.conn.execute(
                "UPDATE departments SET head_id = $1 WHERE department_id = $2",
                head_id,
                dept_id,
            )

            # 6-10 преподавателей на кафедру
            for _ in range(ctx.random.randint(6, 10)):
                teacher_id = await ctx.conn.fetchval(
                    "INSERT INTO staff (full_name, role_id, department_id) VALUES ($1, $2, $3) RETURNING staff_id",
                    _full_name(ctx),
                    role_ids["Преподаватель"],
                    dept_id,
                )
                ctx.staff_ids.append(teacher_id)
                ctx.staff_teachers.append(teacher_id)

        # 1-2 сотрудника на факультет
        for _ in range(ctx.random.randint(1, 2)):
            emp_id = await ctx.conn.fetchval(
                "INSERT INTO staff (full_name, role_id, department_id) VALUES ($1, $2, $3) RETURNING staff_id",
                _full_name(ctx),
                role_ids["Сотрудник"],
                None,
            )
            ctx.staff_ids.append(emp_id)


def _full_name(ctx: SeedContext) -> str:
    return f"{ctx.faker.last_name()} {ctx.faker.first_name()} {ctx.faker.middle_name()}"


async def seed_specialties_groups(ctx: SeedContext) -> None:
    """Создаёт специальности и группы."""
    status_titles = ["Обучается", "Отчислен", "В академическом отпуске", "Выпускник"]
    for title in status_titles:
        ctx.status_ids[title] = await ctx.conn.fetchval(
            "INSERT INTO student_statuses (title) VALUES ($1) RETURNING status_id",
            title,
        )

    for fac_name, fid in ctx.faculty_ids.items():
        for code in SPECIALTY_CODES[fac_name]:
            title = SPECIALTY_TITLES.get(code, f"{fac_name} — {code}")
            sid = await ctx.conn.fetchval(
                "INSERT INTO specialties (code, title, faculty_id, total_semesters) "
                "VALUES ($1, $2, $3, 8) RETURNING specialty_id",
                code,
                title,
                fid,
            )
            ctx.specialty_ids.append(sid)
            ctx.specialty_by_code[code] = sid

    # Группы: по одной на специальность на каждый год набора
    group_num = 1
    for code, sid in ctx.specialty_by_code.items():
        for year in ADMISSION_YEARS:
            gid = await ctx.conn.fetchval(
                "INSERT INTO groups (title, specialty_id, admission_year) VALUES ($1, $2, $3) RETURNING group_id",
                f"{code.split('.')[1]}-{str(year)[2:]}-{group_num}",
                sid,
                year,
            )
            ctx.group_ids.append(gid)
            group_num += 1


async def seed_students(ctx: SeedContext) -> None:
    """Создаёт студентов (~500)."""
    # Группы по (специальность, год набора)
    groups_by_spec_year: dict[tuple[int, int], int] = {}
    for row in await ctx.conn.fetch(
        "SELECT group_id, specialty_id, admission_year FROM groups"
    ):
        groups_by_spec_year[(row["specialty_id"], row["admission_year"])] = row[
            "group_id"
        ]

    used_passports: set[str] = set()
    target = 500
    created = 0
    attempts = 0
    max_attempts = target * 50

    # Статусы: большая часть «Обучается», часть «Отчислен», «Выпускник», «Академ.»
    while created < target and attempts < max_attempts:
        attempts += 1
        specialty_id = ctx.random.choice(ctx.specialty_ids)
        # год набора: не позже REFERENCE_YEAR и так, чтобы студент ещё учился
        # admission_year от 2019 до 2025 (не берём 2026 — только поступили)
        admission_year = ctx.random.choice(range(2019, 2026))
        key = (specialty_id, admission_year)
        group_id = groups_by_spec_year.get(key)
        if group_id is None:
            continue

        passport = (
            f"{ctx.random.randint(1000, 9999)} {ctx.random.randint(100000, 999999)}"
        )
        if passport in used_passports:
            continue
        used_passports.add(passport)

        # Статус в зависимости от года поступления
        years_studied = REFERENCE_YEAR - admission_year
        if years_studied >= 7:
            status = "Выпускник"
        elif ctx.random.random() < 0.08:
            status = "Отчислен"
        elif ctx.random.random() < 0.03:
            status = "В академическом отпуске"
        else:
            status = "Обучается"

        await ctx.conn.execute(
            "INSERT INTO students (name, surname, patronymic, passport, specialty_id, group_id, admission_year, status_id) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
            ctx.faker.first_name(),
            ctx.faker.last_name(),
            ctx.faker.middle_name(),
            passport,
            specialty_id,
            group_id,
            admission_year,
            ctx.status_ids[status],
        )
        created += 1

    # Собираем id студентов
    for row in await ctx.conn.fetch("SELECT student_id FROM students"):
        ctx.student_ids.append(row["student_id"])


async def seed_courses_instructors(ctx: SeedContext) -> None:
    """Создаёт дисциплины и назначает преподавателей."""
    # Маппинг: faculty_id -> имя факультета
    fac_by_id: dict[int, str] = {}
    for name, fid in ctx.faculty_ids.items():
        fac_by_id[fid] = name

    # department по факультету (для привязки курса к кафедре)
    dept_of_faculty: dict[int, int] = {}
    for fac_name, depts in ctx.dept_by_faculty.items():
        fid = ctx.faculty_ids[fac_name]
        dept_of_faculty[fid] = depts[0]

    for sid in ctx.specialty_ids:
        row = await ctx.conn.fetchrow(
            "SELECT faculty_id FROM specialties WHERE specialty_id = $1", sid
        )
        fac_name = fac_by_id[row["faculty_id"]]
        dept_id = dept_of_faculty[row["faculty_id"]]

        for semester, titles in CURRICULUM[fac_name].items():
            for title in titles:
                cid = await ctx.conn.fetchval(
                    "INSERT INTO courses (title, department_id, semester, lecture_hours) "
                    "VALUES ($1, $2, $3, $4) RETURNING course_id",
                    title,
                    dept_id,
                    semester,
                    ctx.random.choice([32, 48, 64]),
                )
                ctx.course_ids.append(cid)
                ctx.course_by_faculty_semester.setdefault(
                    (fac_name, semester), []
                ).append(cid)

    # Назначаем преподавателей на курсы (1-2 на курс, из кафедры курса)
    teachers_by_dept: dict[int, list[int]] = {}
    for row in await ctx.conn.fetch(
        "SELECT staff_id, department_id FROM staff WHERE department_id IS NOT NULL"
    ):
        teachers_by_dept.setdefault(row["department_id"], []).append(row["staff_id"])

    for cid in ctx.course_ids:
        dept_id = await ctx.conn.fetchval(
            "SELECT department_id FROM courses WHERE course_id = $1", cid
        )
        candidates = teachers_by_dept.get(dept_id, [])
        if not candidates:
            continue
        n = ctx.random.randint(1, 2)
        chosen = ctx.random.sample(candidates, min(n, len(candidates)))
        for teacher_id in chosen:
            await ctx.conn.execute(
                "INSERT INTO course_instructors (course_id, staff_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                cid,
                teacher_id,
            )


async def seed_academic_records(ctx: SeedContext) -> None:
    """Создаёт записи успеваемости для обучающихся студентов."""
    # Текущий семестр студента: (REFERENCE_YEAR - admission_year)*2 + 1 (осенний)
    # Берём студентов со статусом «Обучается»
    rows = await ctx.conn.fetch(
        """
        SELECT s.student_id, s.admission_year, sp.total_semesters, sp.faculty_id
        FROM students s
        JOIN specialties sp ON sp.specialty_id = s.specialty_id
        JOIN student_statuses st ON st.status_id = s.status_id
        WHERE st.title = 'Обучается'
        """
    )

    fac_by_id: dict[int, str] = {}
    for name, fid in ctx.faculty_ids.items():
        fac_by_id[fid] = name

    total_records = 0
    for row in rows:
        student_id = row["student_id"]
        admission_year = row["admission_year"]
        total_semesters = row["total_semesters"]
        fac_name = fac_by_id[row["faculty_id"]]

        # текущий семестр студента (1-индекс), ограниченный total_semesters
        current_sem = (REFERENCE_YEAR - admission_year) * 2 + REFERENCE_SEMESTER
        current_sem = max(current_sem, 1)
        current_sem = min(current_sem, total_semesters)

        # записи по всем семестрам от 1 до current_sem
        for semester in range(1, current_sem + 1):
            courses = ctx.course_by_faculty_semester.get((fac_name, semester), [])
            for cid in courses:
                # вероятность неаттестации ~7%
                if ctx.random.random() < 0.07:
                    grade = None
                    has_debt = ctx.random.random() < 0.5
                else:
                    # оценка 3-5 (накопит. по 100-балльной, но храним 0-5)
                    grade = round(ctx.random.choice([3, 3.5, 4, 4, 4.5, 5]), 2)
                    has_debt = False
                await ctx.conn.execute(
                    "INSERT INTO academic_records (student_id, course_id, grade, has_debt, semester) "
                    "VALUES ($1, $2, $3, $4, $5)",
                    student_id,
                    cid,
                    grade,
                    has_debt,
                    semester,
                )
                total_records += 1

    print(f"academic_records: {total_records}")


async def seed_rooms_schedule(ctx: SeedContext) -> None:
    """Создаёт аудитории и расписание для текущего семестра."""
    buildings = ["А", "Б", "В", "Г"]
    for b in buildings:
        for floor in range(1, 6):
            for room_num in range(1, 8):
                rid = await ctx.conn.fetchval(
                    "INSERT INTO rooms (building, number, capacity) VALUES ($1, $2, $3) RETURNING room_id",
                    b,
                    f"{floor}{room_num:02d}",
                    ctx.random.choice([20, 25, 30, 40, 50, 80, 100]),
                )
                ctx.room_ids.append(rid)

    # Расписание: для каждой группы берём курсы текущего семестра и раскидываем по слотам
    groups = await ctx.conn.fetch(
        """
        SELECT g.group_id, g.admission_year, sp.faculty_id, sp.total_semesters
        FROM groups g JOIN specialties sp ON sp.specialty_id = g.specialty_id
        """
    )
    fac_by_id: dict[int, str] = {}
    for name, fid in ctx.faculty_ids.items():
        fac_by_id[fid] = name

    slots_created = 0
    for g in groups:
        current_sem = (REFERENCE_YEAR - g["admission_year"]) * 2 + REFERENCE_SEMESTER
        current_sem = max(current_sem, 1)
        current_sem = min(current_sem, g["total_semesters"])
        fac_name = fac_by_id[g["faculty_id"]]
        courses = ctx.course_by_faculty_semester.get((fac_name, current_sem), [])
        weekday = 1
        period = 1
        for cid in courses:
            room_id = ctx.random.choice(ctx.room_ids)
            await ctx.conn.execute(
                "INSERT INTO schedule_slots (course_id, group_id, room_id, weekday, period) "
                "VALUES ($1, $2, $3, $4, $5)",
                cid,
                g["group_id"],
                room_id,
                weekday,
                period,
            )
            slots_created += 1
            period += 1
            if period > 5:
                period = 1
                weekday += 1

    print(f"schedule_slots: {slots_created}")


async def seed_admission(ctx: SeedContext) -> None:
    """Создаёт контрольные цифры приёма и статистику по годам."""
    years = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
    for sid in ctx.specialty_ids:
        for year in years:
            budget = ctx.random.randint(15, 60)
            paid = ctx.random.randint(10, 40)
            await ctx.conn.execute(
                "INSERT INTO admission_plans (year, specialty_id, budget_places, paid_places, application_deadline) "
                "VALUES ($1, $2, $3, $4, $5)",
                year,
                sid,
                budget,
                paid,
                date(year, 7, 25),
            )
            # фактические данные: заявлений больше, зачислено ~бюджет+плат, проходной растёт
            applications = budget + paid + ctx.random.randint(20, 120)
            enrolled = budget + paid
            passing = round(ctx.random.uniform(4.0, 4.8), 2)
            avg = round(passing + ctx.random.uniform(-0.3, 0.3), 2)
            await ctx.conn.execute(
                "INSERT INTO admission_stats (year, specialty_id, applications, enrolled, passing_score, avg_score) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                year,
                sid,
                applications,
                enrolled,
                passing,
                avg,
            )


async def seed_users(ctx: SeedContext) -> None:
    """Создаёт демо-пользователей для проверки ролей."""
    # app.role -> (external_id, internal_id)
    # Берём реальных студентов и преподавателей
    demo_student_id = ctx.student_ids[0] if ctx.student_ids else None
    demo_teacher_id = ctx.staff_teachers[0] if ctx.staff_teachers else None

    # Небольшой набор демо-аккаунтов
    users_data = [
        ("demo_admin", BusinessRole.ADMIN.value, None, "Ректор Иванов"),
        ("demo_applicant", BusinessRole.APPLICANT.value, None, "Абитуриент"),
    ]
    if demo_student_id:
        users_data.append(
            ("demo_student", BusinessRole.STUDENT.value, demo_student_id, "Студент")
        )
    if demo_teacher_id:
        users_data.append(
            ("demo_teacher", BusinessRole.TEACHER.value, demo_teacher_id, "Преподаватель")
        )

    for external_id, role, internal_id, display in users_data:
        await ctx.conn.execute(
            "INSERT INTO users (external_id, role, internal_id, display_name) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (external_id) DO NOTHING",
            external_id,
            role,
            internal_id,
            display,
        )


async def main() -> None:
    conn = await asyncpg.connect(settings.database_url_owner)
    try:
        # Идемпотентность: очищаем всё
        await conn.execute(
            "TRUNCATE schedule_slots, admission_plans, admission_stats, course_instructors, "
            "academic_records, students, groups, courses, rooms, staff, departments, specialties, "
            "student_statuses, roles, faculties, users, query_log RESTART IDENTITY CASCADE"
        )
        ctx = SeedContext(conn)
        ctx.faker.seed_instance(42)

        await seed_faculties_departments(ctx)
        await seed_staff(ctx)
        await seed_specialties_groups(ctx)
        await seed_students(ctx)
        await seed_courses_instructors(ctx)
        await seed_academic_records(ctx)
        await seed_rooms_schedule(ctx)
        await seed_admission(ctx)
        await seed_users(ctx)

        print(f"faculties: {len(ctx.faculty_ids)}")
        print(f"departments: {len(ctx.department_ids)}")
        print(f"staff: {len(ctx.staff_ids)}")
        print(f"specialties: {len(ctx.specialty_ids)}")
        print(f"groups: {len(ctx.group_ids)}")
        print(f"students: {len(ctx.student_ids)}")
        print(f"courses: {len(ctx.course_ids)}")
        print(f"rooms: {len(ctx.room_ids)}")
        print("seed: OK")
    finally:
        await conn.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
