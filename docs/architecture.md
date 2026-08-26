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
   │  3. маскированное описание схемы под пользователя (get_schema)
   │  4. вызов шлюза (передаётся users.id)
   │  5. пересказ результата по-русски вторым LLM-вызовом
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
и ставит `app.student_id`/`app.staff_id` для RLS. Роль строкой не передаётся и
не вводится единый `user_id`: скоуп выводится аддитивно из этих двух id
(гость — только общие таблицы). В `query_log.user_id` пишется номер учётки
(`users.id`). Приложение не знает про доменные id.

Ключевой принцип: **приложение никогда не обращается к базе напрямую**. Весь доступ
идёт только через `db`, где сосредоточены безопасность, валидация, маскирование
схемы и аудит.

> Примечание: пакеты `db_mcp`/`app` в текущем виде описывают старую модель
> доступа (роль строкой, `internal_id`, MCP-шлюз) и будут перестроены с нуля
> под описанную выше set-based модель.

## Пакеты (uv workspace)

### packages/db_mcp
Единственный шлюз доступа к базе данных. Всё, что касается безопасности, живёт здесь:
- `roles.py` — канонический вокабуляр ролей: `BusinessRole`
  (applicant/student/teacher/admin) и `DbPool` (ro/admin/service); единый источник
  для маппинга пулов соединений и RLS-контекста;
- `access.py` — пулы соединений asyncpg по ролям PostgreSQL (`app_ro` /
  `app_admin` / `app_service`) и установка RLS-контекста
  (`set_config('app.role', ...)`, `app.user_id`) в начале транзакции;
  создание пула сериализуется локом (гонка исключена); в транзакции ставится
  `statement_timeout` (10 с по умолчанию) — защита от «зависших» SELECT;
  **резолюция identity**: `connection_for` принимает `user_id` = номер учётки
  (`users.id`), резолвит его в `internal_id` через пул `app_service` и ставит
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
- `audit.py` — запись запросов в `query_log` через выделенную роль `app_service`;
  в `query_log.user_id` пишется номер учётки (`users.id`);
- `userstore.py` — чтение/запись учётных записей (`users`) для auth через роль
  `app_service`;
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
- хранилище учёток — `UserCredentialsStore` (протокол); реализация
  `DbUserCredentialsStore` читает/пишет `users` через шлюз (`manage_user`).


**Конвейер text-to-SQL и REST-слой**:
- `app/gateway/client.py` — MCP-клиент к шлюзу `db_mcp` (stdio): `get_schema(role)`,
  `execute_query(sql, role, user_id=users.id)`, `manage_user(...)`. Сессия MCP
  поднимается лениво при первом обращении и держится до закрытия приложения
  (`Pipeline.close()`);
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
  `/ask`. Авторизованные пользователи ходят в `/ask` с Bearer-токеном —
  `role`/`user_id` бэкенд берёт из JWT.
- **Mock-ассистент** (`src/lib/mock.js`): используется как фолбэк, когда
  бэкенд недоступен (сеть/прокси) и для гостевой сессии (гость не имеет
  токена, а `/ask` требует авторизацию). Отвечает локально, детерминированно,
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
