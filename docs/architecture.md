# Архитектура Baikal

## Общая схема

Проект — **безопасный text-to-SQL коннектор** к университетской PostgreSQL-базе.
Запрос пользователя на естественном языке проходит строгий конвейер и превращается
в валидированный SQL, который исполняется через **единственный шлюз доступа**.

```
Пользователь (HTTP)
   │  POST /ask  { question }
   ▼
packages/app  (FastAPI, тул-агент)
   │  1. аутентификация (JWT: вход по логину/паролю; sub = users.id; гость — без токена)
   │  2. маскированная схема под пользователя (get_schema) → в системный промпт
   │  3. цикл агента: LLM решает, когда вызвать тул execute_query (≤ agent_max_steps)
   │     - execute_query → валидация+RLS+аудит в шлюзе; ошибка → LLM исправляет SQL
   │  4. ответ — NDJSON-поток: status / query / token / done / error
   ▼
packages/db  (ЕДИНСТВЕННЫЙ шлюз к БД)
   │  - резолюция identity: users.id → {student_id, staff_id} (+ роль из staff.position)
   │  - доступ к БД, RLS-контекст (app.student_id / app.staff_id), аудит
   │  - приложение НЕ ходит в БД напрямую
   ▼
PostgreSQL (roles + set-based RLS)
```

**Identity (важно):** шлюз принимает `execute_query(sql, user_id)`, где `user_id` —
**номер учётки** (`users.id`, он же `sub` из JWT). Шлюз сам резолвит через
служебную роль `app_service` два независимых поля — `student_id` и `staff_id` —
и ставит `app.student_id`/`app.staff_id` для RLS. Скоуп выводится аддитивно из
этих двух id (гость — только общие таблицы). В `query_log.user_id` пишется номер
учётки (`users.id`). Приложение не знает про доменные id. Для аудита
`execute_query` принимает ещё `role` — бизнес-роль из приложения (гость →
`"guest"`), пишется в `query_log.role` (см. ADR 16).

Ключевой принцип: **приложение никогда не обращается к базе напрямую**. Весь доступ
идёт только через `db`, где сосредоточены безопасность, валидация, маскирование
схемы и аудит.

> Примечание: пакет `app` перестроен под set-based модель доступа: прямой вызов
> фасада `db.Gateway` (без MCP), роль резолвится на каждый запрос, гость работает
> через `user_id=None`.

## Пакеты (uv workspace)

### packages/db
Пакет работы с базой данных. Единственный шлюз к PostgreSQL: всё, что касается
безопасности, живёт здесь. Роль строкой не хранится и не передаётся — доступ
выводится из `student_id`/`staff_id` пользователя (см. «Модель доступа»).
- `access.py` — пулы соединений asyncpg по двум ролям PostgreSQL (`app_ro` /
  `app_service`); `connection_for(pools, identity)` ставит RLS-контекст
  (`set_config('app.student_id'/'app.staff_id', ..., true)`) в начале транзакции;
  создание пула сериализуется локом (гонка исключена); в транзакции ставится
  `statement_timeout` (10 с по умолчанию) — защита от «зависших» SELECT. Для
  гостя (identity None) ни один GUC не ставится → RLS deny-by-default на
  `students`/`marks`, общие таблицы открыты.
- `identity.py` — резолюция identity: `users.id` → `Identity(student_id,
  staff_id, is_active)` через служебный пул `app_service`; `resolve_role` —
  для app-уровня (известная должность из `staff.position` приоритетнее
  `student`, см. ADR 39).
- `validate.py` — валидация SQL (sqlglot): ровно один read-only запрос —
  SELECT или set-операция (UNION/INTERSECT/EXCEPT), запрет опасных функций
  (включая nextval/pg_advisory_*), запрет DML в любом узле дерева
  (WITH-выражения), запрет FOR UPDATE/FOR SHARE и SELECT INTO по всему дереву,
  гарантированный лимит строк (`MAX_ROWS = 200`); валидный PostgreSQL
  `LIMIT ALL` принимается и зажимается до лимита (fallback при ошибке
  парсинга не искажает литералы);
- `schema.py` — маскированное описание схемы для LLM из живого каталога БД +
  русские описания таблиц; гость не видит `students`/`marks`, любой
  аутентифицированный — все доменные таблицы (скоуп строк задаёт RLS);
  PK/FK для генерации JOIN — из статического `TABLE_META`; PII-колонки
  помечаются метаданными `SENSITIVE_COLUMNS`;
- `audit.py` — запись запросов в `query_log` через роль `app_service`;
  в `query_log.user_id` пишется номер учётки (`users.id`);
- `userstore.py` — чтение/запись учётных записей (`users`) для auth через роль
  `app_service` (без роли/external_id/display_name: только student_id/staff_id);
- `models.py` — pydantic-модели контракта: `Identity`, `QueryResult`,
  `SchemaDescription`, `TableInfo`, `ColumnInfo`, `UserRecord`;
- `gateway.py` — фасад `Gateway` (единая точка входа для приложения).

Фасад `Gateway`:
- `get_schema(user_id)` — маскированное описание схемы под пользователя (для
  генерации SQL). `user_id=None` (гость) → без `students`/`marks`;
- `execute_query(sql, user_id, role=None)` — валидация → резолюция identity →
  исполнение с RLS → аудит. `user_id` здесь — **номер учётки** (`users.id`) или
  None для гостя; скоуп выводит БД. `role` — бизнес-роль для `query_log.role`
  (приходит из приложения; гость → `"guest"`, см. ADR 16). Ответ — `QueryResult`:
  `{columns, rows, row_count, truncated, duration_ms}`, где `rows` — массив
  массивов (по позициям колонок), `columns` берётся из `record.keys()` (порядок
  и дубли сохраняются). Numeric-значения передаются строками без потери
  точности.
- `resolve_identity(user_id)` / `resolve_role(user_id)` — для приложения
  (логин, require_role);
- CRUD учёток: `get_user_by_login`, `get_user`, `list_users`, `create_user`,
  `update_user`, `deactivate_user`, `has_admin`.

### packages/app
FastAPI-приложение: тонкий HTTP-слой поверх `db`. Всего три эндпоинта:

- `POST /api/v1/auth/login` — вход по email/паролю → JWT (`sub` = номер учётки,
  `users.id`). Роль в токен **не кладётся**: она резолвится на каждый запрос.
- `GET /api/v1/auth/users/me` — текущая учётка (`Me`) с производной ролью
  (для бейджа в интерфейсе).
- `POST /api/v1/ask` — тул-агент; ответ — **NDJSON-поток**; **гость разрешён**
  (без токена → `user_id=None`). Запрос ограничен rate limiting (см. ADR 37):
  авторизованный — по `user_id`, гость — по IP; раздельные лимиты.

Учётные записи и их связки `student_id`/`staff_id` заводятся **вне приложения**
(сид / руками в БД): у app нет ни управления учётками, ни write-доступа к
данным. «Админ» в чате — это роль доступа по RLS (видит все строки), а не
административная панель.

Структура (`packages/app/src/app/`):

- `main.py` — `create_app()`: один `Gateway`, контейнер `AppContext(gateway,
  auth, agent)`, lifespan закрывает `Gateway`. Инъекция — через override
  `get_context` (единственный шов DI, используется и тестами).
- `context.py` — `AppContext` (dataclass) и DI-хук `get_context`.
- `auth/schemas.py` — `LoginRequest`, `TokenResponse`, `Me`.
- `auth/deps.py` — `get_current_user` (обязательная auth: нет/невалидный токен
  или неактивная учётка → 401), `get_optional_context` (гость при
  отсутствии/невалидном токене; валидный токен неактивной учётки → 401).
  Идентичность и роль резолвятся через `db.resolve_identity`/`resolve_role`;
  `AuthContext` несёт `can_see_pii = resolve_identity(user_id) is not None`
  (есть RLS-скоуп, см. ADR 38).
- `auth/router.py` — `/login`, `/users/me`.
- `services/auth.py` — `AuthService(gateway)`: `authenticate` (bcrypt с
  dummy-hash против timing-оракла, email нормализуется), `get_me`.
- `agent/` — тул-агент (см. ADR 36):
  - `prompts.py` — системный промпт (read-only SELECT, LIMIT, самокоррекция)
    + `build_system_prompt(schema_text, role, can_see_pii)`: правило PII
    выбирается по `can_see_pii` — разрешено в рамках RLS-скоупа или запрет
    «только агрегаты» для гостя (см. ADR 38);
  - `tools.py` — `EXECUTE_QUERY_SCHEMA` и `ToolExecutor(gateway, user_id)`
    (`ToolResult(content, meta)`; `GatewayError` → текст ошибки);
  - `agent.py` — `Agent.stream(question, user_id, role, can_see_pii)` — цикл
    LLM-вызовов
    (≤ `agent_max_steps`) со стримингом: токены финального текста идут сразу,
    `tool_call_chunks` собираются и исполняются после шага; события
    `status/query/token/done/error`; `AgentError`.
- `llm/` — `llm.py` (`ChatLLM.stream(messages, tools)` через `astream` +
  `bind_tools`, `LLMError`), `render.py` (`schema_to_text`).
- `api/ask.py` — `POST /ask` через `get_optional_context`; отдаёт
  `StreamingResponse` (NDJSON), формат событий — см. ADR 36; перед агентом —
  проверка rate limit (см. ADR 37); в агент прокидывается `can_see_pii`
  пользователя (см. ADR 38);
- `core/` — `config.py` (JWT + LLM + `agent_max_steps` + параметры rate limit),
  `security.py` (bcrypt + JWT RS256), `ratelimit.py` (`SlidingWindowLimiter` —
  скользящее окно по ключу, in-process).

App использует из `db` только: `get_user_by_login`, `get_user`,
`resolve_identity`, `resolve_role`, `get_schema`, `execute_query`.

### frontend (каталог `frontend/`)
React (Vite) SPA — веб-интерфейс по [design.md](design.md). Страницы: лендинг
(`/`), чат (`/chat`), вход (`/login`).
- **Стек:** React 18, react-router-dom, Vite. Никакого UI-фреймворка — свои
  токены/компоненты на CSS-переменных (светлая и тёмная темы).
- **Dev-прокси:** `vite.config.js` проксирует `/api` на FastAPI (`:8000`),
  поэтому в dev не нужен CORS. В проде статика раздаётся FastAPI.
- **API-клиент** (`src/lib/api.js`): `/auth/login`, `/auth/users/me`,
  `/ask`. Авторизованные пользователи ходят в `/ask` с Bearer-токеном;
  бэкенд берёт `user_id` из JWT, а роль резолвит сам (в токене её нет).
- **Mock-ассистент** (`src/lib/mock.js`): используется как фолбэк, когда
  бэкенд недоступен (сеть/прокси) и для гостевой сессии (фронтенд пока не
  подключён к реальному `/ask` гостя — бэкенд уже принимает запросы без
  токена, подключение запланировано). Отвечает локально, детерминированно,
  по фактам засеянной базы (см. [seed.md](seed.md)). Формат ответа совпадает
  с `Answer`/`QueryMeta`.
- **Гостевой доступ:** неавторизованный пользователь работает в отдельной
  гостевой сессии без привязки к бизнес-ролям; роль в интерфейсе не
  показывается (бейдж «Гость»).

## Модель безопасности (3 уровня)

Безопасность строится тремя независимыми слоями, которые усиливают друг друга:

1. **Роли PostgreSQL** (`db/02_roles.sql`), принцип наименьших привилегий:
   - `app_ro` — единственная рабочая read-only роль. SELECT на все доменные
     таблицы; скоуп строк задаёт RLS. Служебные таблицы `users` и `query_log`
     для неё закрыты.
   - `app_service` — служебная роль приложения: запись в `query_log` (аудит),
     чтение/запись `users` (auth) и чтение `staff`/`positions` (резолюция
     identity для RLS). Пользователям недоступна, прав на доменные таблицы
     (кроме колонок staff/positions, нужных для резолюции) не имеет.

2. **Row-Level Security** (`db/03_rls.sql`), deny-by-default, set-based:
   - контекст задаётся шлюзом в начале транзакции **двумя независимыми GUC**:
     `SET LOCAL app.student_id = '<student_id>'; SET LOCAL app.staff_id = '<staff_id>';`
     — роль строкой и единый `user_id` не используются;
   - доступ выводится **аддитивно** из студенческого и/или кадрового id:
     `app.student_id` даёт свою строку в `students` и свои оценки в `marks`;
     `app.staff_id` — скоуп по должности (`teacher` → свои занятия, `head` →
     кафедра, `dean` → факультет, `admin` → всё);
   - без контекста строк не видно (гость видит только общие таблицы без RLS);
   - студент видит только свою строку в `students` и только свои оценки;
   - преподаватель — студентов групп своих занятий и оценки по своим предметам;
   - зав. кафедрой — студентов групп по предметам своей кафедры и оценки по ним;
   - декан — студентов своего факультета и их оценки;
   - администрация видит всё.

## Модель доступа (identity)

- Таблица `users`: `id`, необязательные `student_id`/`staff_id` (связь с
  доменными сущностями), `email` (логин, UNIQUE), `password_hash` (bcrypt),
  `is_active` (деактивация учётки вместо удаления). **Роль строкой не хранится.**
- **Identity в потоке запроса:** JWT `sub` = номер учётки (`users.id`). Шлюз
  принимает `users.id` и сам резолвит через `app_service` два поля —
  `student_id` и `staff_id` — из `users` (а роль персонала — из `staff.position`),
  затем ставит `app.student_id`/`app.staff_id` для RLS. Приложение не знает про
  доменные id; они задаются при создании учётки.
- **Гость:** запрос без `user_id` (или у пользователя нет ни `student_id`, ни
  `staff_id`) — RLS deny-by-default на `students`/`marks`, открыты только общие
  таблицы (факультеты, направления, аудитории, расписание, приёмная кампания и
  т.п.). Это соответствует сценарию «абитуриент/гость».
- Роли бизнес-уровня и PII-политика описаны в [roles.md](roles.md).
- Пользователь с обоими id получает **объединение** скоупов студента и
  сотрудника.

## Схема БД

22 таблицы: `buildings`, `faculties`, `departments`, `specializations`, `groups`,
`student_statuses`, `students`, `positions`, `staff`, `subjects`, `terms`,
`classrooms`, `lessons`, `lesson_group`, `marks`, `users`, `admission_campaigns`,
`admission_committees`, `admission_committee_members`, `admission_plans`,
`admission_stats`, `query_log`. Полное определение — в `db/01_schema.sql`.
Ключевые особенности:
- `users` не хранит роль — она выводится динамически (`student_id` → студент,
  `staff_id` → роль из `staff.position`);
- `students.name/surname/patronymic` — персональные данные; видимость задаёт
  RLS (кто видит строку студента, тот видит и её PII-поля);
- служебные `users`/`query_log` закрыты для бизнес-роли.
