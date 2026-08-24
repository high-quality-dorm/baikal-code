# Синтетические данные (сид)

Генератор: `scripts/seed.py`. Запуск: `make seed` (выполняет
`uv run python scripts/seed.py`). Скрипт подключается к БД как `app_owner`
(через `DATABASE_URL_OWNER` из `.env`).

## Параметры

- Библиотека: `faker` (локаль `ru_RU`), добавлен в dev-зависимости.
- **Детерминированность:** `seed=42` — генерация воспроизводима.
- **Референс-дата:** `2026-09-15`:
  - `REFERENCE_YEAR = 2026`
  - `REFERENCE_SEMESTER = 1` (1 = осень, 2 = весна)
  - «Текущий семестр» вычисляется от этой даты.
- **Идемпотентность:** перед генерацией выполняется
  `TRUNCATE ... RESTART IDENTITY CASCADE` — скрипт можно запускать повторно.

## Объёмы данных

| Таблица             | Количество  |
| ------------------- | ----------- |
| faculties           | 5           |
| departments         | 11          |
| staff               | 111         |
| specialties         | 26          |
| groups              | 208         |
| students            | 500         |
| courses             | 645         |
| academic_records    | 40 531      |
| rooms               | 140         |
| schedule_slots      | 3 350       |
| admission_plans     | 182         |
| admission_stats     | 182         |

## Демо-пользователи

Таблица `users` содержит 4 записи (external_id → роль + внутренний id):

| external_id    | role    | internal_id |
| -------------- | ------- | ----------- |
| demo_applicant | applicant | —           |
| demo_student   | student | student_id 1 |
| demo_teacher   | teacher | staff_id 4   |
| demo_admin     | admin   | —           |

## Верификация RLS на данных

Контекст RLS задаётся в начале транзакции:
`SET LOCAL app.role = 'student' | 'teacher' | 'admin'; SET LOCAL app.user_id = '<internal_id>';`

Проверенная матрица (на засеянных данных):

| Роль      | Что видит                                                                   |
| --------- | --------------------------------------------------------------------------- |
| student   | только свои записи (`academic_records`), только свою строку в `students`    |
| teacher   | только оценки по своим курсам (через `course_instructors`)                  |
| admin     | все записи и всех студентов, включая PII (name/surname/patronymic/passport) |

Пример (студент): с `app.role='student'`, `app.user_id='1'` — 120 своих записей из
40 531 в таблице; в `students` — 1 строка.

## Замечания по реализации

- Курсы привязаны к кафедре факультета; преподаватели назначаются **из кафедры курса**
  (1–2 на курс) — для корректной работы RLS-политики преподавателя.
- PII-поля студентов (`name`, `surname`, `patronymic`, `passport`) генерируются
  детерминированно и уникальны (passport — с проверкой уникальности).