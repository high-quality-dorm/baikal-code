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
   │  1. аутентификация/идентификация (JWT: вход по логину/паролю)
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
- `roles.py` — канонический вокабуляр ролей: `BusinessRole`
  (applicant/student/teacher/admin) и `DbPool` (ro/admin/audit); единый источник
  для маппинга пулов соединений и RLS-контекста;
- `access.py` — пулы соединений asyncpg по ролям PostgreSQL (`app_ro` /
  `app_admin` / `app_audit`) и установка RLS-контекста
  (`set_config('app.role', ...)`, `app.user_id`) в начале транзакции;
  создание пула сериализуется локом (гонка исключена); в транзакции ставится
  `statement_timeout` (10 с по умолчанию) — защита от «зависших» SELECT;
- `validate.py` — валидация SQL (sqlglot): ровно один read-only запрос —
  SELECT или set-операция (UNION/INTERSECT/EXCEPT), запрет опасных функций
  (включая nextval/pg_advisory_*), запрет DML в любом узле дерева
  (WITH-выражения), запрет FOR UPDATE/FOR SHARE и SELECT INTO по всему дереву,
  гарантированный лимит строк (`MAX_ROWS = 200`);
- `schema.py` — маскированное описание схемы для LLM из живого каталога БД
  (PII-колонки скрываются на уровне прав роли) + русские описания таблиц;
- `audit.py` — запись запросов в `query_log` через выделенную роль `app_audit`;
- `server.py` — MCP-сервер (mcp 2.0, класс `MCPServer`) на stdio-транспорте.

Инструменты MCP-сервера:
- `get_schema(role)` — маскированное описание схемы под роль (для генерации SQL);
- `execute_query(sql, role, user_id)` — валидация → исполнение с RLS → аудит.
  Ответ: `{columns, rows, row_count, truncated, duration_ms}`, где `rows` —
  массив массивов (по позициям колонок), `columns` берётся из `record.keys()`
  (порядок и дубли сохраняются). Numeric-значения передаются строками без
  потери точности.

**Доменные сущности БД** — в `packages/db_mcp/src/db_mcp/models.py`. PII-поля
студентов (`name`, `surname`, `patronymic`, `passport`) помечены комментарием
`# sensitive`: доступны только роли администрации, для остальных ролей физически
скрыты (колоночные гранты) и не попадают в описание схемы для LLM. Список
PII-колонок для маскирования описания схемы — в `schema.py` (`SENSITIVE_COLUMNS`).

### packages/app
FastAPI-приложение: сам конвейер text-to-SQL поверх `db_mcp`.
**API-схемы** — в `packages/app/src/app/api/schemas.py`: `Role`
(applicant/student/teacher/admin), `Question`, `Answer`, `QueryMeta`.

**Auth-подсистема** (`packages/app/src/app/auth/` + `core/security.py` + `services/`):
- вход по логину/паролю → JWT access-токен (RS256), подписанный RSA-ключом;
  роль и идентификатор учётки (`sub`) берутся из токена; пароли хэшируются bcrypt;
- эндпоинты `/api/v1/auth/login` и `/api/v1/auth/bootstrap-admin` (создание первого
  админа, только если админов ещё нет);
- администратор управляет учётными записями: `POST/GET/PATCH/DELETE /api/v1/auth/users`;
- хранилище учёток — `UserCredentialsStore` (протокол); сейчас подключён мок
  `InMemoryAuthStore`, реальное хранилище через `db_mcp` — отдельный будущий этап.

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
  Для auth добавлены колонки: `email` (логин, UNIQUE), `password_hash` (bcrypt),
  `is_active` (деактивация учётки вместо удаления).
- Роли бизнес-уровня (applicant/student/teacher/admin) и PII-политика описаны в
  [roles.md](roles.md).
- Канонические значения ролей — `BusinessRole` в
  `packages/db_mcp/src/db_mcp/roles.py`; маппинг бизнес-ролей на пулы
  PostgreSQL — единый словарь `_BUSINESS_ROLE_TO_POOL` в `access.py`.

## Схема БД

17 таблиц: `faculties`, `departments`, `roles`, `staff`, `specialties`,
`student_statuses`, `groups`, `students`, `courses`, `course_instructors`,
`academic_records`, `rooms`, `schedule_slots`, `admission_plans`, `admission_stats`,
`users`, `query_log`. Полное определение — в `db/01_schema.sql`.

Почему выбран PostgreSQL 16 и остальные решения — см. [decisions.md](decisions.md).
