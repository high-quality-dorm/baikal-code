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

## Что дальше

Работа идёт **поэтапно**. Каждый этап делится на шаги; каждый шаг — реализация →
`make check` → коммит → объяснение пользователю → подтверждение на следующий.
Этапы связаны и идут в порядке: шлюз → auth → конвейер.

### Этап 13 — Шлюз: резолюция identity (packages/db_mcp)
Цель: MCP-инструмент `execute_query` принимает **номер учётки** (`users.id`),
а шлюз сам резолвит его в доменный `internal_id` (student_id/staff_id) через
служебную роль `app_audit`. Приложение не знает про `internal_id`.

- [x] **Шаг 13.1** Права: `app_audit` получает `SELECT (id, internal_id) ON users`
      (нужно резолверу). Обновить `docs/roles.md`, ADR.
- [x] **Шаг 13.2** Резолвер `resolve_internal_id(pools, user_id)`:
      `SELECT internal_id FROM users WHERE id = $1` через пул `app_audit`.
      `connection_for` резолвит `user_id` и ставит `app.user_id = internal_id`.
      Несуществующий `users.id`/NULL → `app.user_id` не ставится (настройка
      отсутствует → deny по RLS, безопасно, без ошибки). RLS-политики не меняются.
- [x] **Шаг 13.3** Аудит: в `query_log.user_id` писать номер учётки (`users.id`),
      а не резолвленный `internal_id`.
- [x] **Шаг 13.4** Контракт: в MCP-инструменте параметр `user_id` документально
      трактуется как `users.id` (номер учётки); описание инструмента обновить.
- [x] **Шаг 13.5** Тесты: резолвер (найден/NULL/несуществующий), NULL-поведение
      `connection_for`, аудит с `users.id`. Обновить `test_access`, `test_server`.
- [x] `make check`, `make test` → коммит → стоп → объяснение.

### Этап 14 — Auth: internal_id в учётках (packages/app)
Цель: админ при создании учётки вручную указывает `internal_id` (student_id/
staff_id). JWT `sub` остаётся номером учётки (`users.id`) — контракт токена не
меняется; резолюцию выполняет шлюз (этап 13).

- [ ] **Шаг 14.1** `UserCreate.internal_id: int | None` (админ задаёт вручную).
- [ ] **Шаг 14.2** `AuthService.create_user` пробрасывает `internal_id` в
      `Credentials`; bootstrap-админ → `internal_id=None`.
- [ ] **Шаг 14.3** Роутер `POST /auth/users` принимает `internal_id`. Проверки
      существования студента/преподавателя нет — неверный ID даёт пустой RLS.
- [ ] **Шаг 14.4** Тесты создания учётки с `internal_id`; обновить
      `test_api`, `test_auth`; обновить `docs/roles.md`, `docs/architecture.md`.
- [ ] `make check`, `make test` → коммит → стоп → объяснение.

### Этап 15 — Конвейер text-to-SQL + POST /api/v1/ask (packages/app)
Цель: полноценный `/ask`: схема под роль → LLM генерирует SQL → шлюз исполняет
(RLS) → LLM пересказывает ответ по-русски.

- [ ] **Шаг 15.1** Зависимость `langchain-openai`; конфиг LLM
      (`llm_base_url`, `llm_api_key`, `llm_model`, `llm_temperature`),
      `db_mcp_command`; `.env.example`.
- [ ] **Шаг 15.2** MCP-клиент `app/gateway/client.py`: stdio-запуск `db_mcp`,
      `get_schema(role)`, `execute_query(sql, role, user_id=users.id)`.
- [ ] **Шаг 15.3** LLM-клиент `app/llm/llm.py` (OpenAI-совместимый, base_url/
      model/key из конфига) + `app/llm/prompts.py` (только read-only SELECT,
      лимиты, PII, безопасность).
- [ ] **Шаг 15.4** Конвейер `app/services/pipeline.py`:
      schema → SQL → execute → NL-ответ → `Answer`.
- [ ] **Шаг 15.5** Роутер `POST /api/v1/ask` (`Question` + auth) → `Answer`;
      подключить в `main.py`.
- [ ] **Шаг 15.6** Тесты: `test_pipeline` (фейк LLM + фейк шлюз), `test_ask`.
- [ ] **Шаг 15.7** Обновить `docs/architecture.md`, `docs/decisions.md`,
      `docs/roadmap.md`, `docs/index.md`; `make check`, `make test` → коммит →
      стоп → объяснение.

### После (вне текущего цикла)
- Реальное хранилище учёток `UserCredentialsStore` на основе `db_mcp`
  (сейчас auth работает на in-memory моке). Требует admin-write в шлюзе
  (запись в `users`), что выходит за read-only рамки — отдельный этап.
- Заполнение реальных значений LLM (`base_url`/`model`/`key`) в `.env` —
  делается вручную при эксплуатации.

## Текущее состояние

- База заполнена синтетикой (см. [seed.md](seed.md)).
- RLS работает: студент видит только своё, преподаватель — только свои курсы,
  администрация — всё (включая PII).
- Шлюз `db_mcp` работает как MCP-сервер на stdio: валидация SQL, исполнение
  с RLS-контекстом (шлюз резолвит `users.id` → `internal_id` через
  `app_audit`), маскирование схемы под роль, аудит в `query_log`
  (запросы — только SELECT, лимит строк 200).
- Auth реализован (JWT по логину/паролю, управление учётками), но хранилище
  учёток пока in-memory — подключение к `db_mcp` впереди.

## Открытые блокеры

- **Docker Hub недоступен** (TLS timeout) — используется кэшированный образ
  `postgres:16-alpine` вместо 17.