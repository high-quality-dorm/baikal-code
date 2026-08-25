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

## Что дальше

Работа идёт **поэтапно**. Каждый этап: реализация → `make check` → коммит →
**стоп и объяснение пользователю** → ожидание подтверждения на следующий этап.

### Этап 17 — Реальное хранилище учёток (packages/db_mcp, packages/app)
Цель: заменить in-memory мок `InMemoryAuthStore` на реальное хранилище
`UserCredentialsStore` поверх `db_mcp`. Требует admin-write в шлюзе (запись
в `users`), что выходит за текущие read-only рамки — отдельный этап.

- [ ] **Шаг 17.1** Admin-write в шлюзе: write-инструмент для `users`
      (create/update/delete) через роль `app_admin`/отдельную служебную роль.
- [ ] **Шаг 17.2** `UserCredentialsStore` на основе шлюза: чтение
      `email`/`password_hash`/`role`/`internal_id`/`is_active` для auth.
- [ ] **Шаг 17.3** Подключение хранилища в `AuthService`; демонтаж мока.
- [ ] **Шаг 17.4** Тесты, `make check`, `make test` → коммит → стоп → объяснение.

### После (вне текущего цикла)
- Заполнение реальных значений LLM (`base_url`/`model`/`key`) в `.env` —
  делается вручную при эксплуатации.
- Ретрай LLM при ошибке шлюза (см. ADR 24) — осознанно отложен.
- Страницы управления учётками для администратора в фронтенде
  (см. [design.md](design.md)).

## Текущее состояние

- База заполнена синтетикой (см. [seed.md](seed.md)).
- RLS работает: студент видит только своё, преподаватель — только свои курсы,
  администрация — всё (включая PII).
- Шлюз `db_mcp` работает как MCP-сервер на stdio: валидация SQL, исполнение
  с RLS-контекстом (шлюз резолвит `users.id` → `internal_id` через
  `app_audit`), маскирование схемы под роль, аудит в `query_log`
  (запросы — только SELECT, лимит строк 200).
- Auth реализован (JWT по логину/паролю, управление учётками, админ задаёт
  `internal_id`), но хранилище учёток пока in-memory — подключение к `db_mcp`
  впереди.
- Конвейер `/api/v1/ask` реализован: схема под роль → генерация SQL через LLM →
  исполнение через шлюз → пересказ по-русски. Реальные значения LLM
  заполняются в `.env` вручную.

## Открытые блокеры

- **Docker Hub недоступен** (TLS timeout) — используется кэшированный образ
  `postgres:16-alpine` вместо 17.