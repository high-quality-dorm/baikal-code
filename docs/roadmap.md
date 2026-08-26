# Роадмап и прогресс Baikal

## Как мы работаем

- Работа идёт **поэтапно**. Каждый этап: реализация → `make check` → коммит →
  **стоп и объяснение пользователю** → ожидание подтверждения на следующий этап.
- Ветка: `dev`.

## Что завершено

| # | Этап | Содержание | Коммит |
| - | ---- | ---------- | ------ |
| 1 | Workspace | Перестройка в uv workspace: `packages/db_mcp` + `packages/app`; Makefile (sync/run/db/seed/format/check/test) | `0ceb261` |
| 2 | Модели | Доменные сущности БД → `db_mcp/models.py`; API-схемы → `app/api/schemas.py` | `37318c8` |
| 3 | БД в docker | PostgreSQL 16 (docker-compose); схема (17 таблиц), роли, RLS; верифицирована матрица RLS | `6968339` |
| 4 | Сид | Генератор синтетики `scripts/seed.py` (faker, детерминированный); RLS проверен на данных | `5a64992` |
| 5 | Ядро db_mcp | Модули шлюза `access`/`validate`/`schema`/`audit`; MCP-сервер (mcp 2.0, `get_schema`/`execute_query`); валидация sqlglot; аудит в `query_log`; тесты | `c80b1cc` |
| 6 | Auth | JWT-аутентификация по логину/паролю (bcrypt), bootstrap-админ, CRUD учёток админом; расширение `users` (email/password_hash/is_active); пока на in-memory моке | `7ba4413` |
| 7 | Роли db_mcp (E) | Канонический вокабуляр `BusinessRole`/`DbPool` в `roles.py`; единый маппинг пулов, `Pools.pool`/`dsn_for`; тесты маппинга и согласованности с RLS | `11a9637` |
| 8 | Укрепление шлюза (A) | `statement_timeout` в транзакции (10 с), сериализация создания пулов локом; ужесточение валидации: FOR UPDATE/FOR SHARE, DML в любом узле дерева, расширенный чёрный список функций | `edc5f88`, `f547e38` |
| 9 | Set-операции (B) | Валидация принимает UNION/UNION ALL/INTERSECT/EXCEPT с зажимом верхнего LIMIT; SELECT INTO проверяется по всему дереву (INTO у UNION на первом операнде) | `99f6818` |
| 10 | Корректность ответа (C) | Ответ `execute_query` — `columns`/`rows` (дубли колонок сохраняются, numeric строкой без потери точности); `LIMIT ALL` принимается и зажимается | `a71bc30`, `aa26c29` |
| 11 | Схема для LLM (D) | PK/FK в описании схемы (статический `TABLE_META` — `primary_key`/`foreign_keys`) для генерации JOIN; тест-инвариант: PII-колонки не PK и не цели FK | `d899ea4` |
| 12 | Роли в app и seed (E2) | app зависит от `db-mcp`; enum `Role` удалён, везде `BusinessRole`; `require_role(*BusinessRole)`; демо-роли сида через `BusinessRole` | `d2c69f8`, `ed67079` |
| 13 | Резолюция identity | Грант `app_audit` на `users(id, internal_id)`; `resolve_internal_id` + `connection_for` (users.id → internal_id для RLS); аудит пишет `users.id`; контракт MCP-инструмента обновлён | `f88d2f1`, `1fed9d4`, `60a0eaf` |
| 14 | internal_id в учётках | `UserCreate.internal_id` (ge=1); `create_user` пробрасывает его в `Credentials`; bootstrap-админ → None; контракт JWT `sub` = users.id не меняется | `82c082f` |
| 15 | Конвейер text-to-SQL | `langchain-openai` + конфиг LLM; MCP-клиент шлюза; LLM-клиент и промпты; `Pipeline`; `POST /api/v1/ask`; тесты | `745bd97`, `59d4343`, `3e3748f`, `8a3bd03`, `70bfc13` |
| 16 | Frontend | React SPA (Vite) в `frontend/`: лендинг, чат, вход; токены/темы; гостевой доступ; вход через `/auth/login`; `/ask` подключён с Bearer-токеном; mock — фолбэк для гостя и при недоступном бэкенде | `7ec8a3b`, `f36848f`, `5b69462` |
| 17 | Реальное хранилище учёток | `DbUserCredentialsStore` поверх шлюза (инструмент `manage_user`); запись/чтение `users` через служебную роль; `app_audit` → `app_service`; сид демо-учёток с паролями; демонтаж мока `InMemoryAuthStore` | (текущий) |
| 18 | DB v2: set-based доступ | Схема 22 таблицы (`specializations`/`subjects`/`marks`/`lessons`/`admission_*` и др.); роли выводятся из `student_id`/`staff_id` (нет колонки роли); RLS на `app.student_id`/`app.staff_id` (без `app.role`/`app.user_id`); отказ от `app_admin` (два пула); гость = абитуриент без id; сид: демо-пользователи 5 ролей + гость; матрица RLS верифицирована | `bb7cb41` |
| 19 | Пакет db вместо db_mcp | Переименование `db_mcp` → `db`; пакет как библиотека (фасад `Gateway`: `get_schema(user_id)`, `execute_query(sql, user_id)`, резолюция identity, CRUD учёток) без MCP-сервера; два пула (`app_ro`/`app_service`); pydantic-модели контракта; `roles.py` удалён (роль производная); тесты переехали в `tests/db/`; app временно исключён из проверок до ребилда | (текущий) |
| 20 | App перестроен на db.Gateway | Пакет `app` пересобран с нуля как тонкий HTTP-слой: три эндпоинта (`/auth/login`, `/auth/users/me`, `/ask`); роль резолвится на каждый запрос (`resolve_role`), в JWT только `sub`; гость работает через `user_id=None` (реальный бэкенд, mock — фолбэк); MCP-клиент и админ-CRUD учёток удалены (учётки ведутся вне приложения); `AppContext` — единый шов DI; тесты переписаны, `make check`/`test` включают `packages/app` | `4f74977`, `5374d86`, `3aa8ec9` |
| 21 | Тул-агент со стримингом | `/ask` перестроен на тул-агента: LLM в цикле (≤ `agent_max_steps`) вызывает тул `execute_query` (обёртка над `db.Gateway`), видит ошибки шлюза и самокорректируется; ответ — NDJSON-поток (`status`/`query`/`token`/`done`/`error`), финальный текст стримится токенами (`astream`); `Pipeline`/`generate_sql`/`answer` удалены; ADR 24 заменена ADR 36; тесты переписаны (181), live-проверка tool-calling на Yandex подтверждена | `2e59e23`, `4d07b43` |
| 22 | Фронт под тул-агента | Фронтенд подключён к реальному `/ask`: гость и авторизованный идут в бэкенд (mock — только при недоступном бэкенде); отрисовка NDJSON-потока (`status` — строка этапов с пульсацией, `token` — живой текст, `done` — SQL/мета); кнопка «Остановить» (AbortController); бейджи ролей `head`/`dean`, email вместо `display_name`, «Пользователь» для учётки без роли | (этап работы) |
| 23 | Rate limiting для /ask | `SlidingWindowLimiter` (скользящее окно, in-process) в `core/ratelimit.py`; раздельные лимиты: авторизованный по `user_id`, гость по IP; параметры в `.env` (`RATE_LIMIT_*`); 429 при превышении; лимитер — одиночка в `AppContext`; ADR 37; тесты (188) | `c002345` |
| 24 | PII по RLS-скоупу | `AuthContext.can_see_pii = resolve_identity != None` (есть RLS-скоуп, а не роль); проброс через `Agent.stream` в `build_system_prompt(schema_text, role, can_see_pii)`: True — PII разрешён в рамках скоупа, False (гость) — «только агрегаты»; RLS/схема не меняются; ADR 38; тесты (195) | `46682fa` |
| 25 | Приоритет должности в resolve_role | В `resolve_role` известная должность (`teacher/head/dean/admin`) приоритетнее `student`; неизвестная должность не маскирует студента; доступ (RLS) не меняется — только представление роли; ADR 39; тесты (197) | `c1dc4e3` |
| 26 | Реальная роль в аудите | `Gateway.execute_query(sql, user_id, role)` пишет роль в `query_log.role`; роль приходит из приложения (`Agent` → `ToolExecutor`), гость → `"guest"` вместо `NULL`; аудит не роняет запрос; ADR 16 уточнена; тесты (199) | (этап 26, текущий) |

## Что дальше

Работа идёт **поэтапно**. Каждый этап: реализация → `make check` → коммит →
**стоп и объяснение пользователю** → ожидание подтверждения на следующий этап.

### После (вне текущего цикла)
- **Устранение замечаний бэкенда** (поэтапный план — [fixes.md](fixes.md)):
  rate limit, PII по RLS-скоупу, приоритет должности в `resolve_role` и реальная
  роль в аудите — **все выполнены** (этапы 23–26).
- Заполнение реальных значений LLM (`base_url`/`model`/`key`) в `.env` —
  делается вручную при эксплуатации.
- Раздельная БД auth (вынести `users`/`query_log` в отдельную базу приложения) —
  опция на случай мультитенантности/отдельной доменной инфраструктуры; на
  текущем масштабе избыточно (см. ADR 27).

## Текущее состояние

- База переведена на **schema v2** (22 таблицы) и заполнена синтетикой
  (см. [seed.md](seed.md)).
- **Set-based модель доступа:** роль не хранится в `users`, а выводится из
  `student_id`/`staff_id` (для персонала — из `staff.position`). RLS работает от
  двух GUC (`app.student_id`/`app.staff_id`), без `app.role` и единого
  `app.user_id`. Два пула: `app_ro` + `app_service`.
- RLS верифицирован на данных: гость не видит `students`/`marks`; студент —
  только своё; преподаватель/зав.кафедрой/декан — свой скоуп; администрация —
  всё (матрица в [seed.md](seed.md)).
- Пакет **`db`** (бывший `db_mcp`) — библиотека: фасад `Gateway`
  (`get_schema(user_id)`, `execute_query(sql, user_id, role)` — роль для аудита,
  резолюция identity, CRUD учёток), валидация SQL (sqlglot), маскирование схемы
  под пользователя, аудит в `query_log` (реальная роль, гость → `"guest"`,
  см. ADR 16). MCP-сервер удалён (может вернуться как опциональная обёртка при
  необходимости tool-based агента). `roles.py` удалён — роль производная.
- Пакет **`app`**: `/ask` — **тул-агент** со стримингом (NDJSON:
  `status`/`query`/`token`/`done`/`error`); агент в цикле вызывает тул
  `execute_query`, видит ошибки шлюза и самокорректируется (ADR 36); финальный
  текст стримится токенами. Роль резолвится на каждый запрос (`resolve_role`,
  в JWT только `sub`), гость работает через `user_id=None`. Учётные записи и
  связки `student_id`/`staff_id` заводятся вне приложения. `AppContext` —
  единый контейнер сервисов и шов DI. Устранены замечания бэкенда (этапы
  23–26, план — [fixes.md](fixes.md)): `/ask` ограничен rate limiting (ADR 37),
  PII доступен по RLS-скоупу (`can_see_pii`, ADR 38), в `query_log` пишется
  реальная роль.
- `make format`/`check`/`test` работают по `packages/db` + `packages/app`
  (`pytest tests/` — 199 тестов). Реальные значения LLM заполняются в `.env`
  вручную.