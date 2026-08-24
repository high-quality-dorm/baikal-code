# Архитектура Baikal

## Общая схема

Проект — **безопасный text-to-SQL коннектор** к университетской PostgreSQL-базе.
Запрос пользователя на естественном языке проходит строгий конвейер и превращается
в валидированный SQL, который исполняется через **единственный шлюз доступа**.

```
Пользователь (HTTP)
   │  POST /ask  { question, роль, user_id }
   ▼
packages/app  (FastAPI, конвейер text-to-SQL)
   │  1. аутентификация/идентификация (прототип: заголовки)
   │  2. генерация SQL через LLM (LangChain, OpenAI-совместимый API)
   │  3. валидация и маскирование схемы под роль
   │  4. вызов шлюза (MCP, stdio transport)
   ▼
packages/db_mcp  (ЕДИНСТВЕННЫЙ шлюз к БД)
   │  - доступ к БД, RLS-контекст, аудит запросов
   │  - приложение НЕ ходит в БД напрямую
   ▼
PostgreSQL (roles + column-masking + RLS)
```

Ключевой принцип: **приложение никогда не обращается к базе напрямую**. Весь доступ
идёт только через `db_mcp`, где сосредоточены безопасность, валидация, ролевое
маскирование схемы и аудит.

## Пакеты (uv workspace)

### packages/db_mcp
Единственный шлюз доступа к базе данных. Всё, что касается безопасности, живёт здесь:
- доступ к PostgreSQL (asyncpg);
- установка RLS-контекста (`SET LOCAL app.role`, `app.user_id`);
- ролевое маскирование описания схемы (PII-колонки скрываются от роли);
- аудит запросов (запись в `query_log`);
- FastMCP-сервер поверх этого.

**Доменные сущности БД** — в `packages/db_mcp/src/db_mcp/models.py`. PII-поля
помечены `sensitive=True` (студенты: `name`, `surname`, `patronymic`, `passport`).
Они доступны только роли администрации и маскируются для остальных ролей, не попадая
в описание схемы для LLM.

### packages/app
FastAPI-приложение: сам конвейер text-to-SQL поверх `db_mcp`.
**API-схемы** — в `packages/app/src/app/api/schemas.py`: `Role`
(applicant/student/teacher/admin), `Question`, `Answer`, `QueryMeta`.
Роль и идентификатор пользователя передаются заголовками `X-Role` и `X-User-Id`
(прототип auth без SSO).

## Модель безопасности (3 уровня)

Безопасность строится тремя независимыми слоями, которые усиливают друг друга:

1. **Роли PostgreSQL** (`db/02_roles.sql`):
   - `app_ro` — рабочая read-only роль. SELECT на все таблицы, но **без** PII-колонок
     студентов (`name`, `surname`, `patronymic`, `passport`) и без служебных таблиц
     `users`, `query_log`.
   - `app_admin` — как `app_ro` + права на PII-колонки студентов.
   - `app_audit` — только чтение/запись в `query_log`.

2. **Колоночное сокрытие PII** — даже если роль угадана, колонки персональных данных
   физически недоступны для `app_ro`. Сначала снимается табличный SELECT со `students`,
   затем выдаётся SELECT только на безопасные колонки (иначе табличная привилегия
   перекрывает колоночный REVOKE).

3. **Row-Level Security** (`db/03_rls.sql`), deny-by-default:
   - контекст задаётся приложением в начале транзакции:
     `SET LOCAL app.role = 'student' | 'teacher' | 'admin'; SET LOCAL app.user_id = '<internal_id>';`
   - без контекста строк не видно;
   - студент видит только свою строку в `students` и только свои оценки;
   - преподаватель видит оценки только по своим курсам;
   - администрация видит всё.

## Модель доступа (identity)

- Таблица `users`: маппинг внешнего пользователя на внутренние идентификаторы:
  `external_id` → `role` + `internal_id` (student_id или staff_id) + `display_name`.
- Роли бизнес-уровня (applicant/student/teacher/admin) и PII-политика описаны в
  [about.md](about.md).

## Схема БД

17 таблиц: `faculties`, `departments`, `roles`, `staff`, `specialties`,
`student_statuses`, `groups`, `students`, `courses`, `course_instructors`,
`academic_records`, `rooms`, `schedule_slots`, `admission_plans`, `admission_stats`,
`users`, `query_log`. Полное определение — в `db/01_schema.sql`.

Почему выбран PostgreSQL 16 и остальные решения — см. [decisions.md](decisions.md).
