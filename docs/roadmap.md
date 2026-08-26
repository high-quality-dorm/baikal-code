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

## Что дальше

Работа идёт **поэтапно**. Каждый этап: реализация → `make check` → коммит →
**стоп и объяснение пользователю** → ожидание подтверждения на следующий этап.

### После (вне текущего цикла)
- Заполнение реальных значений LLM (`base_url`/`model`/`key`) в `.env` —
  делается вручную при эксплуатации.
- Ретрай LLM при ошибке шлюза (см. ADR 24) — осознанно отложен.
- Страницы управления учётками для администратора во фронтенде
  (см. [design.md](design.md)).
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
- Пакет **`db`** (бывший `db_mcp`) перестроен как библиотека: фасад `Gateway`
  (`get_schema(user_id)`, `execute_query(sql, user_id)`, резолюция identity,
  CRUD учёток), валидация SQL (sqlglot), маскирование схемы под пользователя,
  аудит в `query_log`. MCP-сервер удалён (может вернуться как опциональная
  обёртка при необходимости tool-based агента). `roles.py` удалён — роль
  производная.
- Auth и конвейер `/api/v1/ask` в пакете `app` — **заморожены** (исключены из
  проверок) и будут перестроены с нуля: роль резолвится в момент логина через
  `db.resolve_role`, `student_id`/`staff_id` вместо `internal_id`, прямой вызов
  `Gateway` вместо MCP-клиента.
- `make format`/`check`/`test` работают по `packages/db` и `tests/db/` (134
  теста). Реальные значения LLM заполняются в `.env` вручную.