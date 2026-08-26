"""Генератор синтетических данных для БД университета (Baikal v2).

Идемпотентный: перед наполнением делает TRUNCATE ... RESTART IDENTITY CASCADE
всех таблиц. Детерминированный (seed=42). Подключается как app_owner (владелец
схемы) из .env (DATABASE_URL_OWNER).

Точка входа: `make seed` или `uv run python scripts/seed.py`.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from datetime import date

import asyncpg
import bcrypt
from faker import Faker
from pydantic_settings import BaseSettings, SettingsConfigDict

# Опорная точка «текущего семестра»: осень 2026/27 учебного года.
REFERENCE_YEAR = 2026
REFERENCE_SEMESTER = 1  # 1 = осень, 2 = весна
TOTAL_SEMESTERS = 8


class Settings(BaseSettings):
    """Настройки подключения для сида."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url_owner: str = "postgresql://app_owner:owner@localhost:5432/university"


settings = Settings()

ADMISSION_YEARS = list(range(2019, 2027))

FACULTIES = [
    ("ИВТ и информатика", "Факультет информационных технологий"),
    ("Экономика и управление", "Экономический факультет"),
    ("Гуманитарные науки", "Гуманитарный факультет"),
    ("Естественные науки", "Факультет естественных наук"),
    ("Инженерия и технологии", "Инженерно-технический факультет"),
]

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

# Учебный план по факультетам: типовые дисциплины на каждый семестр (1-8).
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

STUDENT_STATUSES = [
    ("Обучается", True),
    ("Академический отпуск", False),
    ("Отчислен", False),
    ("Выпускник", False),
]

POSITIONS = ["teacher", "head", "dean", "admin"]

BUILDINGS = ["А", "Б", "В", "Г"]


@dataclass
class SeedContext:
    """Накопленные id вставленных сущностей (для связывания FK)."""

    conn: asyncpg.Connection
    faker: Faker = field(default_factory=lambda: Faker("ru_RU"))
    rng: random.Random = field(default_factory=lambda: random.Random(42))

    term_by_key: dict[tuple[int, int], int] = field(default_factory=dict)
    faculty_ids: dict[str, int] = field(default_factory=dict)
    dept_ids: list[int] = field(default_factory=list)
    dept_by_faculty: dict[str, list[int]] = field(default_factory=dict)
    spec_ids: list[int] = field(default_factory=list)
    spec_by_code: dict[str, int] = field(default_factory=dict)
    spec_faculty: dict[int, str] = field(default_factory=dict)
    group_ids: list[int] = field(default_factory=list)
    group_by_spec_year: dict[tuple[int, int], int] = field(default_factory=dict)
    group_meta: dict[int, tuple[str, int, int]] = field(default_factory=dict)
    status_ids: dict[str, int] = field(default_factory=dict)
    position_ids: dict[str, int] = field(default_factory=dict)
    staff_ids: list[int] = field(default_factory=list)
    teacher_ids: list[int] = field(default_factory=list)
    admin_ids: list[int] = field(default_factory=list)
    teachers_by_dept: dict[int, list[int]] = field(default_factory=dict)
    staff_by_faculty: dict[str, list[int]] = field(default_factory=dict)
    dean_by_faculty: dict[str, int] = field(default_factory=dict)
    head_by_dept: dict[int, int] = field(default_factory=dict)
    subject_by_key: dict[tuple[str, int, str], int] = field(default_factory=dict)
    subject_dept_by_key: dict[tuple[str, int, str], int] = field(default_factory=dict)
    room_ids: list[int] = field(default_factory=list)
    student_ids: list[int] = field(default_factory=list)
    student_meta: dict[int, tuple[int, int, int, str]] = field(default_factory=dict)
    campaign_by_year: dict[int, int] = field(default_factory=dict)


# Размер пачки для batch-вставки. Пачки убирают сетевые round-trip'ы: на
# удалённой БД (~75 мс/statement) поодиночная вставка ~20k строк занимала бы
# десятки минут, пачками — единицы секунд.
BATCH_SIZE = 500


async def _insert_rows(
    conn: asyncpg.Connection, base_sql: str, rows: list[tuple], batch: int = BATCH_SIZE
) -> list[int]:
    """Пакетная INSERT ... RETURNING id (multi-row VALUES).

    `base_sql` — INSERT без `VALUES` (например "INSERT INTO students (a, b)").
    id возвращаются в том же порядке, что и строки в `rows`.
    """
    ids: list[int] = []
    if not rows:
        return ids
    cols = len(rows[0])
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        counter = itertools.count(1)
        placeholders = ",".join(
            "(" + ",".join(f"${next(counter)}" for _ in range(cols)) + ")"
            for _ in chunk
        )
        flat = [v for row in chunk for v in row]
        recs = await conn.fetch(f"{base_sql} VALUES {placeholders} RETURNING id", *flat)
        ids.extend(r["id"] for r in recs)
    return ids


async def _exec_many(
    conn: asyncpg.Connection, base_sql: str, rows: list[tuple], batch: int = BATCH_SIZE
) -> None:
    """Пакетная вставка без необходимости получать id (executemany)."""
    if not rows:
        return
    for i in range(0, len(rows), batch):
        await conn.executemany(base_sql, rows[i : i + batch])


async def seed_terms(ctx: SeedContext) -> None:
    """Семестры: осень (year, 1) и весна (year, 2), до «текущего» включительно."""
    rows = []
    for year in ADMISSION_YEARS:
        for sem, start, end in (
            (1, date(year, 9, 1), date(year, 12, 31)),
            (2, date(year + 1, 2, 1), date(year + 1, 6, 30)),
        ):
            if (year, sem) > (REFERENCE_YEAR, REFERENCE_SEMESTER):
                continue
            rows.append((year, sem, start, end))
    ids = await _insert_rows(
        ctx.conn, "INSERT INTO terms (year, semester, date_start, date_end)", rows
    )
    for (year, sem, _s, _e), tid in zip(rows, ids):
        ctx.term_by_key[(year, sem)] = tid


async def seed_positions_statuses(ctx: SeedContext) -> None:
    """Справочники должностей и статусов студентов."""
    pids = await _insert_rows(
        ctx.conn, "INSERT INTO positions (title)", [(t,) for t in POSITIONS]
    )
    ctx.position_ids = dict(zip(POSITIONS, pids))

    titles = [t for t, _ in STUDENT_STATUSES]
    sids = await _insert_rows(
        ctx.conn,
        "INSERT INTO student_statuses (title, is_studying)",
        list(STUDENT_STATUSES),
    )
    ctx.status_ids = dict(zip(titles, sids))


async def seed_faculties_departments(ctx: SeedContext) -> None:
    """Факультеты и кафедры (по 2-3 на факультет)."""
    fids = await _insert_rows(
        ctx.conn, "INSERT INTO faculties (title)", [(n,) for n, _ in FACULTIES]
    )
    ctx.faculty_ids = dict(zip([n for n, _ in FACULTIES], fids))
    ctx.dept_by_faculty = {n: [] for n, _ in FACULTIES}

    d_rows, d_meta = [], []
    for name, _title in FACULTIES:
        for i in range(ctx.rng.randint(2, 3)):
            d_rows.append((f"{name} — кафедра №{i + 1}", ctx.faculty_ids[name]))
            d_meta.append(name)
    dids = await _insert_rows(
        ctx.conn, "INSERT INTO departments (title, faculty_id)", d_rows
    )
    ctx.dept_ids = list(dids)
    for name, did in zip(d_meta, dids):
        ctx.dept_by_faculty[name].append(did)


async def seed_specializations_groups(ctx: SeedContext) -> None:
    """Направления подготовки и группы (по одной на направление на год набора)."""
    s_rows = [
        (fid, code, SPECIALTY_TITLES.get(code, f"{name} — {code}"))
        for name, fid in ctx.faculty_ids.items()
        for code in SPECIALTY_CODES[name]
    ]
    sids = await _insert_rows(
        ctx.conn, "INSERT INTO specializations (faculty_id, code, title)", s_rows
    )
    ctx.spec_ids = list(sids)
    idx = 0
    for name in ctx.faculty_ids:
        for code in SPECIALTY_CODES[name]:
            sid = sids[idx]
            idx += 1
            ctx.spec_by_code[code] = sid
            ctx.spec_faculty[sid] = name

    group_num = 1
    g_rows, g_meta = [], []
    for code, sid in ctx.spec_by_code.items():
        for year in ADMISSION_YEARS:
            title = f"{code.split('.')[1]}-{str(year)[2:]}-{group_num}"
            g_rows.append((sid, title, year))
            g_meta.append((code, sid, year))
            group_num += 1
    gids = await _insert_rows(
        ctx.conn,
        "INSERT INTO groups (specialization_id, title, admission_year)",
        g_rows,
    )
    ctx.group_ids = list(gids)
    for (code, sid, year), gid in zip(g_meta, gids):
        ctx.group_by_spec_year[(sid, year)] = gid
        ctx.group_meta[gid] = (code, sid, year)


async def seed_staff(ctx: SeedContext) -> None:
    """Ректор, деканы, зав. кафедрами, преподаватели и администрация."""
    plan: list[tuple[str, str | None, int | None]] = [("admin", None, None)]  # ректор
    for name in ctx.faculty_ids:
        plan.append(("dean", name, None))
        for dept_id in ctx.dept_by_faculty[name]:
            plan.append(("head", name, dept_id))
            for _ in range(ctx.rng.randint(6, 10)):
                plan.append(("teacher", name, dept_id))
        for _ in range(ctx.rng.randint(1, 2)):
            plan.append(("admin", name, None))

    rows = [
        (
            ctx.faculty_ids[fn] if fn else None,
            dept_id,
            ctx.position_ids[pos],
            ctx.faker.first_name(),
            ctx.faker.last_name(),
            ctx.faker.middle_name(),
        )
        for pos, fn, dept_id in plan
    ]
    ids = await _insert_rows(
        ctx.conn,
        "INSERT INTO staff (faculty_id, department_id, position_id, name, surname, patronymic)",
        rows,
    )
    ctx.staff_ids = list(ids)

    for sid, (pos, fn, dept_id) in zip(ids, plan):
        if pos == "admin":
            ctx.admin_ids.append(sid)
        if fn:
            ctx.staff_by_faculty.setdefault(fn, []).append(sid)
        if pos == "teacher":
            ctx.teacher_ids.append(sid)
            ctx.teachers_by_dept.setdefault(dept_id, []).append(sid)
        elif pos == "dean":
            ctx.dean_by_faculty[fn] = sid
            await ctx.conn.execute(
                "UPDATE faculties SET dean_id = $1 WHERE id = $2",
                sid,
                ctx.faculty_ids[fn],
            )
        elif pos == "head":
            ctx.head_by_dept[dept_id] = sid
            await ctx.conn.execute(
                "UPDATE departments SET head_id = $1 WHERE id = $2", sid, dept_id
            )


async def seed_subjects(ctx: SeedContext) -> None:
    """Дисциплины по учебному плану; распределены по кафедрам факультета."""
    rows, meta = [], []
    for name in ctx.faculty_ids:
        depts = ctx.dept_by_faculty[name]
        for sem in range(1, TOTAL_SEMESTERS + 1):
            for title in CURRICULUM[name].get(sem, []):
                dept = depts[(sem - 1) % len(depts)]
                rows.append((title, dept))
                meta.append((name, sem, title, dept))
    ids = await _insert_rows(
        ctx.conn, "INSERT INTO subjects (title, department_id)", rows
    )
    for (name, sem, title, dept), sid in zip(meta, ids):
        ctx.subject_by_key[(name, sem, title)] = sid
        ctx.subject_dept_by_key[(name, sem, title)] = dept


async def seed_rooms(ctx: SeedContext) -> None:
    """Здания и аудитории."""
    bids = await _insert_rows(
        ctx.conn, "INSERT INTO buildings (title)", [(b,) for b in BUILDINGS]
    )
    bmap = dict(zip(BUILDINGS, bids))
    rows = []
    for b in BUILDINGS:
        for floor in range(1, 6):
            for num in range(1, 8):
                rows.append(
                    (
                        bmap[b],
                        f"{floor}{num:02d}",
                        ctx.rng.choice([20, 25, 30, 40, 50, 80, 100]),
                    )
                )
    cids = await _insert_rows(
        ctx.conn, "INSERT INTO classrooms (building_id, number, capacity)", rows
    )
    ctx.room_ids = list(cids)


def _current_sem(ctx: SeedContext, admission_year: int) -> int:
    """Номер текущего семестра студента (1-индекс), ограниченный TOTAL_SEMESTERS."""
    sem = (REFERENCE_YEAR - admission_year) * 2 + REFERENCE_SEMESTER
    return max(1, min(sem, TOTAL_SEMESTERS))


def _term_for(ctx: SeedContext, admission_year: int, sem_index: int) -> int:
    """term_id для семестра с номером sem_index от поступления студента."""
    year = admission_year + (sem_index - 1) // 2
    sem = 1 + (sem_index - 1) % 2
    return ctx.term_by_key[(year, sem)]


async def seed_students(ctx: SeedContext) -> None:
    """Студенты (~500), со статусами и группой."""
    target = 500
    created = 0
    attempts = 0
    max_attempts = target * 100
    rows, meta = [], []
    while created < target and attempts < max_attempts:
        attempts += 1
        spec = ctx.rng.choice(ctx.spec_ids)
        year = ctx.rng.choice(range(2019, 2027))
        gid = ctx.group_by_spec_year.get((spec, year))
        if gid is None:
            continue
        current_sem = (REFERENCE_YEAR - year) * 2 + REFERENCE_SEMESTER
        if current_sem > TOTAL_SEMESTERS:
            status = "Выпускник"
        elif ctx.rng.random() < 0.08:
            status = "Отчислен"
        elif ctx.rng.random() < 0.03:
            status = "Академический отпуск"
        else:
            status = "Обучается"
        rows.append(
            (
                gid,
                ctx.status_ids[status],
                year,
                ctx.faker.first_name(),
                ctx.faker.last_name(),
                ctx.faker.middle_name(),
            )
        )
        meta.append((gid, spec, year, status))
        created += 1

    ids = await _insert_rows(
        ctx.conn,
        "INSERT INTO students (group_id, status_id, admission_year, name, surname, patronymic)",
        rows,
    )
    ctx.student_ids = list(ids)
    for sid, m in zip(ids, meta):
        ctx.student_meta[sid] = m


async def seed_lessons(ctx: SeedContext) -> None:
    """Занятия для каждой группы по всем пройденным семестрам."""
    l_rows, l_meta = [], []
    for gid in ctx.group_ids:
        _code, spec_id, year = ctx.group_meta[gid]
        fac = ctx.spec_faculty[spec_id]
        for n in range(1, _current_sem(ctx, year) + 1):
            term_id = _term_for(ctx, year, n)
            weekday, period = 1, 1
            for title in CURRICULUM[fac].get(n, []):
                subj = ctx.subject_by_key[(fac, n, title)]
                dept = ctx.subject_dept_by_key[(fac, n, title)]
                teachers = ctx.teachers_by_dept.get(dept, [])
                teacher = ctx.rng.choice(teachers) if teachers else None
                if teacher is None:
                    continue
                room = ctx.rng.choice(ctx.room_ids)
                l_rows.append((subj, room, teacher, term_id, weekday, period))
                l_meta.append(gid)
                period += 1
                if period > 5:
                    period = 1
                    weekday += 1
    lids = await _insert_rows(
        ctx.conn,
        "INSERT INTO lessons (subject_id, classroom_id, teacher_id, term_id, weekday, period)",
        l_rows,
    )
    await _exec_many(
        ctx.conn,
        "INSERT INTO lesson_group (lesson_id, group_id) VALUES ($1, $2)",
        [(lid, gid) for lid, gid in zip(lids, l_meta)],
    )
    print(f"lessons: {len(lids)}")


async def seed_marks(ctx: SeedContext) -> None:
    """Успеваемость по всем пройденным семестрам (5-балльная шкала)."""
    rows = []
    for sid, (_gid, spec_id, year, _status) in ctx.student_meta.items():
        fac = ctx.spec_faculty[spec_id]
        for n in range(1, _current_sem(ctx, year) + 1):
            term_id = _term_for(ctx, year, n)
            for title in CURRICULUM[fac].get(n, []):
                subj = ctx.subject_by_key[(fac, n, title)]
                if ctx.rng.random() < 0.07:
                    grade = None
                    has_debt = ctx.rng.random() < 0.5
                else:
                    grade = ctx.rng.choice([3, 3.5, 4, 4, 4.5, 5])
                    has_debt = False
                rows.append((sid, subj, term_id, grade, has_debt))
    await _exec_many(
        ctx.conn,
        "INSERT INTO marks (student_id, subject_id, term_id, grade, has_debt) "
        "VALUES ($1, $2, $3, $4, $5)",
        rows,
    )
    print(f"marks: {len(rows)}")


async def seed_admission(ctx: SeedContext) -> None:
    """Приёмные кампании, комиссии, планы и статистика приёма."""
    cids = await _insert_rows(
        ctx.conn,
        "INSERT INTO admission_campaigns (year)",
        [(y,) for y in ADMISSION_YEARS],
    )
    ctx.campaign_by_year = dict(zip(ADMISSION_YEARS, cids))

    com_rows, com_meta = [], []
    for year in ADMISSION_YEARS:
        cid = ctx.campaign_by_year[year]
        for name, fid in ctx.faculty_ids.items():
            com_rows.append(
                (
                    cid,
                    fid,
                    ctx.dean_by_faculty[name],
                    f"Корпус А, {name}",
                    f"+7 (495) 000-{year % 100:02d}",
                    f"priem{year}@university.ru",
                    "Пн-Пт 10:00-17:00",
                )
            )
            com_meta.append((cid, name))
    com_ids = await _insert_rows(
        ctx.conn,
        "INSERT INTO admission_committees "
        "(campaign_id, faculty_id, head_staff_id, location, phone, email, working_hours)",
        com_rows,
    )

    mem_rows = []
    for (cid, name), comid in zip(com_meta, com_ids):
        candidates = ctx.staff_by_faculty.get(name, [])
        for staff_id in ctx.rng.sample(
            candidates, min(ctx.rng.randint(2, 3), len(candidates))
        ):
            mem_rows.append((comid, staff_id))
    await _exec_many(
        ctx.conn,
        "INSERT INTO admission_committee_members (committee_id, staff_id) VALUES ($1, $2)",
        mem_rows,
    )

    plan_rows, stat_rows = [], []
    for year in ADMISSION_YEARS:
        cid = ctx.campaign_by_year[year]
        for spec in ctx.spec_ids:
            budget = ctx.rng.randint(15, 60)
            paid = ctx.rng.randint(10, 40)
            plan_rows.append((cid, spec, budget, paid, date(year, 7, 25)))
            applications = budget + paid + ctx.rng.randint(20, 120)
            enrolled = budget + paid
            passing = round(ctx.rng.uniform(3.5, 4.8), 2)
            avg = round(min(5.0, max(0.0, passing + ctx.rng.uniform(-0.3, 0.3))), 2)
            stat_rows.append((cid, spec, applications, enrolled, passing, avg))
    await _exec_many(
        ctx.conn,
        "INSERT INTO admission_plans "
        "(campaign_id, specialization_id, budget_places, paid_places, application_deadline) "
        "VALUES ($1, $2, $3, $4, $5)",
        plan_rows,
    )
    await _exec_many(
        ctx.conn,
        "INSERT INTO admission_stats "
        "(campaign_id, specialization_id, applications, enrolled, passing_score, avg_score) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        stat_rows,
    )


async def seed_users(ctx: SeedContext) -> None:
    """Демо-пользователи платформы (маппинг на студентов/сотрудников).

    student_id/staff_id — необязательные расширители доступа. demo_user без
    обоих id видит только общую информацию (как гость) — проверка пути
    «пользователь без идентичности».
    """
    demo_password = "password123"
    demo_hash = bcrypt.hashpw(demo_password.encode(), bcrypt.gensalt()).decode()

    entries: list[tuple[str, int | None, int | None]] = []
    if ctx.student_ids:
        entries.append(("demo_student", ctx.student_ids[0], None))
    if ctx.teacher_ids:
        entries.append(("demo_teacher", None, ctx.teacher_ids[0]))
    if ctx.head_by_dept:
        first_dept = ctx.dept_by_faculty[next(iter(ctx.faculty_ids))][0]
        entries.append(("demo_head", None, ctx.head_by_dept[first_dept]))
    if ctx.dean_by_faculty:
        entries.append(
            ("demo_dean", None, ctx.dean_by_faculty[next(iter(ctx.faculty_ids))])
        )
    if ctx.admin_ids:
        entries.append(("demo_admin", None, ctx.admin_ids[0]))
    entries.append(("demo_user", None, None))

    await _exec_many(
        ctx.conn,
        "INSERT INTO users (student_id, staff_id, email, password_hash, is_active) "
        "VALUES ($1, $2, $3, $4, TRUE) ON CONFLICT (email) DO NOTHING",
        [
            (student_id, staff_id, f"{external_id}@example.com", demo_hash)
            for external_id, student_id, staff_id in entries
        ],
    )


async def main() -> None:
    conn = await asyncpg.connect(settings.database_url_owner)
    try:
        # Вся вставка — в одной транзакции (идемпотентность + атомарность), а
        # строки вставляются пачками (см. _insert_rows/_exec_many): так сид
        # быстр и на удалённой БД с большим сетевым round-trip'ом.
        async with conn.transaction():
            # Идемпотентность: очищаем всё
            await conn.execute(
                "TRUNCATE admission_stats, admission_plans, admission_committee_members, "
                "admission_committees, admission_campaigns, marks, lesson_group, lessons, "
                "terms, subjects, staff, positions, students, student_statuses, groups, "
                "specializations, departments, faculties, buildings, classrooms, users, "
                "query_log RESTART IDENTITY CASCADE"
            )
            ctx = SeedContext(conn)
            ctx.faker.seed_instance(42)

            await seed_terms(ctx)
            await seed_positions_statuses(ctx)
            await seed_faculties_departments(ctx)
            await seed_specializations_groups(ctx)
            await seed_staff(ctx)
            await seed_subjects(ctx)
            await seed_rooms(ctx)
            await seed_students(ctx)
            await seed_lessons(ctx)
            await seed_marks(ctx)
            await seed_admission(ctx)
            await seed_users(ctx)

        print(f"faculties: {len(ctx.faculty_ids)}")
        print(f"departments: {len(ctx.dept_ids)}")
        print(f"specializations: {len(ctx.spec_ids)}")
        print(f"groups: {len(ctx.group_ids)}")
        print(f"staff: {len(ctx.staff_ids)}")
        print(f"teachers: {len(ctx.teacher_ids)}")
        print(f"students: {len(ctx.student_ids)}")
        print(f"rooms: {len(ctx.room_ids)}")
        print("seed: OK")
    finally:
        await conn.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
