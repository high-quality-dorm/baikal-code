# Архитектура Baikal

## Общая схема

Проект — **безопасный text-to-SQL коннектор** к университетской PostgreSQL-базе.
Запрос пользователя на естественном языке проходит строгий конвейер и превращается
в валидированный SQL, который исполняется через **единственный шлюз доступа**.

```
Пользователь (HTTP)
   │  POST /ask  { question }
   ▼
packages/app  (FastAPI, конвейер text-to-SQL)
   │  1. аутентификация (JWT: вход по логину/паролю; sub = users.id)
   │  2. генерация SQL через LLM (OpenAI-совместимый API, конфигурируемый)
   │  3. ролевое маскирование схемы (get_schema)
   │  4. вызов шлюза (MCP, stdio transport; передаётся users.id)
   │  5. пересказ результата по-русски вторым LLM-вызовом
   ▼
packages/db_mcp  (ЕДИНСТВЕННЫЙ шлюз к БД)
   │  - резолюция users.id → internal_id (через app_audit)
   │  - доступ к БД, RLS-контекст (app.user_id = internal_id), аудит
   │  - приложение НЕ ходит в БД напрямую
   ▼
PostgreSQL (roles + column-masking + RLS)
```

**Identity (важно):** шлюз принимает `execute_query(sql, role, user_id)`, где
`user_id` — **номер учётки** (`users.id`, он же `sub` из JWT). Шлюз сам резолвит
его в доменный `internal_id` (student_id/staff_id) через служебную роль
`app_audit` и ставит `app.user_id = internal_id` для RLS. В `query_log.user_id`
пишется номер учётки (`users.id`). Приложение не знает про `internal_id`.

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
  **резолюция identity**: `connection_for` принимает `user_id` = номер учётки
  (`users.id`), резолвит его в `internal_id` через пул `app_audit` и ставит
  `app.user_id = internal_id`. Если internal_id отсутствует (admin/applicant,
  несуществующий `users.id`) — `app.user_id` не ставится вовсе: PostgreSQL
  хранит NULL в GUC как пустую строку, которая ломала бы политику
  преподавателя (`current_setting(...)::int`); без настройки
  `current_setting('app.user_id', true)` даёт NULL → RLS deny-by-default.
- `validate.py` — валидация SQL (sqlglot): ровно один read-only запрос —
  SELECT или set-операция (UNION/INTERSECT/EXCEPT), запрет опасных функций
  (включая nextval/pg_advisory_*), запрет DML в любом узле дерева
  (WITH-выражения), запрет FOR UPDATE/FOR SHARE и SELECT INTO по всему дереву,
  гарантированный лимит строк (`MAX_ROWS = 200`); валидный PostgreSQL
  `LIMIT ALL` принимается и зажимается до лимита (fallback при ошибке
  парсинга не искажает литералы);
- `schema.py` — маскированное описание схемы для LLM из живого каталога БД
  (PII-колонки скрываются на уровне прав роли) + русские описания таблиц;
  PK/FK для генерации JOIN — из статического `TABLE_META`;
- `audit.py` — запись запросов в `query_log` через выделенную роль `app_audit`;
  в `query_log.user_id` пишется номер учётки (`users.id`);
- `server.py` — MCP-сервер (mcp 2.0, класс `MCPServer`) на stdio-транспорте.

Инструменты MCP-сервера:
- `get_schema(role)` — маскированное описание схемы под роль (для генерации SQL);
- `execute_query(sql, role, user_id)` — валидация → резолюция identity →
  исполнение с RLS → аудит. `user_id` здесь — **номер учётки** (`users.id`),
  а не доменный ID; резолюцию в `internal_id` выполняет сам шлюз.
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
FastAPI-приложение: сам конвейер text-to-SQL поверх `db_mcp`. Пакет зависит от
`db-mcp` (workspace) и переиспользует его канонический вокабуляр ролей
`BusinessRole` вместо собственного enum.
**API-схемы** — в `packages/app/src/app/api/schemas.py`:
`Question`, `Answer`, `QueryMeta`.

**Auth-подсистема** (`packages/app/src/app/auth/` + `core/security.py` + `services/`):
- вход по логину/паролю → JWT access-токен (RS256), подписанный RSA-ключом;
  роль и идентификатор учётки (`sub`) берутся из токена; пароли хэшируются bcrypt;
  `sub` = номер учётки (`users.id`);
- эндпоинты `/api/v1/auth/login` и `/api/v1/auth/bootstrap-admin` (создание первого
  админа, только если админов ещё нет);
- администратор управляет учётными записями: `POST/GET/PATCH/DELETE /api/v1/auth/users`;
  при создании учётки админ вручную указывает `internal_id` (student_id/staff_id) —
  резолюцию в RLS выполняет шлюз; неверный `internal_id` даёт пустой доступ по RLS;
- хранилище учёток — `UserCredentialsStore` (протокол); сейчас подключён мок
  `InMemoryAuthStore`, реальное хранилище через `db_mcp` — отдельный будущий этап.

**Конвейер text-to-SQL и REST-слой**:
- `app/gateway/client.py` — MCP-клиент к шлюзу `db_mcp` (stdio): `get_schema(role)`,
  `execute_query(sql, role, user_id=users.id)`. Сессия MCP поднимается лениво при
  первом обращении и держится до закрытия приложения (`Pipeline.close()`);
- `app/llm/` — конфигурируемый OpenAI-совместимый LLM-клиент
  (`langchain-openai`, `ChatOpenAI`; `llm_base_url`/`llm_api_key`/`llm_model`/
  `llm_temperature` из `Settings`) и системные промпты (`prompts.py`: только
  read-only SELECT, лимиты, PII — второй слой защиты поверх шлюза);
- `app/services/pipeline.py` — конвейер: схема под роль → генерация SQL через LLM →
  исполнение через шлюз (с `users.id`) → пересказ результата по-русски вторым
  LLM-вызовом → `Answer` с метаданными запроса (`QueryMeta`). Ошибка шлюза
  (`GatewayError`) возвращается пользователю без ретрая LLM;
- `POST /api/v1/ask` (`Question` + auth) → `Answer`; `role`/`user_id` берутся из
  JWT (`sub` = номер учётки), контекст доступа задаёт шлюз по RLS.

### frontend (каталог `frontend/`)
React (Vite) SPA — веб-интерфейс по [design.md](design.md). Страницы: лендинг
(`/`), чат (`/chat`), вход (`/login`).
- **Стек:** React 18, react-router-dom, Vite. Никакого UI-фреймворка — свои
  токены/компоненты на CSS-переменных (светлая и тёмная темы).
- **Dev-прокси:** `vite.config.js` проксирует `/api` на FastAPI (`:8000`),
  поэтому в dev не нужен CORS. В проде статика раздаётся FastAPI.
- **API-клиент** (`src/lib/api.js`): `/auth/login`, `/auth/users/me`,
  `/ask`. Заголовки `X-Role` / `X-User-Id` для конвейера text-to-SQL.
- **Mock-ассистент** (`src/lib/mock.js`): пока бэкенд-эндпоинт `/api/v1/ask`
  не реализован, фронтенд при недоступности бэкенда отвечает локально,
  детерминированно, по фактам засеянной базы (см. [seed.md](seed.md)).
  Формат ответа совпадает с `Answer`/`QueryMeta`.
- **Гостевой доступ:** неавторизованный пользователь работает в отдельной
  гостевой сессии без привязки к бизнес-ролям; роль в интерфейсе не
  показывается (бейдж «Гость»).

## Модель безопасности (3 уровня)

Безопасность строится тремя независимыми слоями, которые усиливают друг друга:

1. **Роли PostgreSQL** (`db/02_roles.sql`):
   - `app_ro` — рабочая read-only роль. SELECT на все таблицы, но **без** PII-колонок
     студентов (`name`, `surname`, `patronymic`, `passport`) и без служебных таблиц
     `users`, `query_log`.
   - `app_admin` — как `app_ro` + права на PII-колонки студентов.
   - `app_audit` — запись в `query_log` + `SELECT (id, internal_id) ON users`
     (нужно шлюзу для резолюции identity; служебная роль, пользователям недоступна).

2. **Колоночное сокрытие PII** — даже если роль угадана, колонки персональных данных
   физически недоступны для `app_ro`. Сначала снимается табличный SELECT со `students`,
   затем выдаётся SELECT только на безопасные колонки (иначе табличная привилегия
   перекрывает колоночный REVOKE).

3. **Row-Level Security** (`db/03_rls.sql`), deny-by-default:
   - контекст задаётся шлюзом в начале транзакции:
     `SET LOCAL app.role = 'student' | 'teacher' | 'admin'; SET LOCAL app.user_id = '<internal_id>';`
     где `internal_id` шлюз резолвит из `users.id`;
   - без контекста строк не видно;
   - студент видит только свою строку в `students` и только свои оценки;
   - преподаватель видит оценки только по своим курсам;
   - администрация видит всё.

## Модель доступа (identity)

- Таблица `users`: маппинг внешнего пользователя на внутренние идентификаторы:
  `external_id` → `role` + `internal_id` (student_id или staff_id) + `display_name`.
  Для auth добавлены колонки: `email` (логин, UNIQUE), `password_hash` (bcrypt),
  `is_active` (деактивация учётки вместо удаления).
- **Identity в потоке запроса:** JWT `sub` = номер учётки (`users.id`). Шлюз
  `execute_query` принимает `users.id` и сам резолвит его в `internal_id` через
  `app_audit` (`SELECT internal_id FROM users WHERE id = $1`), затем ставит
  `app.user_id = internal_id` для RLS. В `query_log.user_id` пишется `users.id`.
  Приложение не знает про `internal_id`; админ задаёт его при создании учётки.
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
