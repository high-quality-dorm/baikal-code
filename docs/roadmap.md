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

## Что дальше

Запланированные этапы улучшения `db_mcp` и приложения. Каждый — реализация →
`make check` → коммит → объяснение пользователю → подтверждение на следующий.

### Этап E. Унификация маппингов ролей в db_mcp
- Новый модуль `db_mcp/roles.py`: канонический вокабуляр ролей —
  `BusinessRole(str, Enum)` (applicant/student/teacher/admin) и `DbPool(Enum)`
  (ro/admin/audit). Единый источник вместо констант в `access.py`.
- `access.py`: единый словарь `_BUSINESS_ROLE_TO_POOL: dict[BusinessRole, DbPool]`;
  `BUSINESS_ROLES` выводится из `BusinessRole`; один метод `Pools.pool(db_pool)`
  и `Settings.dsn_for(db_pool)`; `pool_for_role` нормализует `BusinessRole(role)`;
  удалить строковые ключи «ro/admin», ветку `key == "admin"` и дублирующую
  проверку роли в `connection_for`.
- Тесты: `test_access.py` (маппинг всех ролей, нормализация, `UnknownRoleError`),
  новый `test_roles.py` (литералы ролей в `db/03_rls.sql` ⊆ `BusinessRole`).
- Docs: `architecture.md` (единый источник ролей), `decisions.md` (новый ADR),
  `roles.md` — в рамках этапа.

### Этап E2. Роли в app и seed (после E)
- `app`: зависимость `db-mcp` в `pyproject.toml`; удалить enum `Role` из
  `api/schemas.py`; везде `BusinessRole`; `require_role(*BusinessRole)`;
  правки `auth/schemas.py`, `services/auth.py`.
- `scripts/seed.py`: демо-роли через `BusinessRole`.
- Docs: `architecture.md` (app зависит от db_mcp), `roles.md`.

### Этап A. Устойчивость и валидация (критичные)
- `statement_timeout` (10 с по умолчанию, настройка в `Settings`) в начале
  транзакции `connection_for` — защита от «зависших» SELECT (сейчас тяжёлый
  запрос может держать соединение пула вечно).
- Фикс гонки ленивого создания пулов в `Pools._get` (`asyncio.Lock` +
  пере-проверка) — иначе два параллельных первых обращения создают два пула.
- Запрет `FOR UPDATE` / `FOR SHARE` в `validate.py` (defense-in-depth).
- Расширение `FORBIDDEN_FUNCTIONS`: `nextval`/`currval`/`setval`,
  `pg_advisory_*`, `pg_notify`, `lo_open/close/unlink/put/truncate`,
  `pg_export_snapshot`.
- **Закрыть гэп валидации**: DML в любом узле дерева. Сейчас
  `WITH del AS (DELETE ... RETURNING *) SELECT * FROM del` проходит проверку
  (корень — `Select`), блокируется только грантами БД. Отклонять
  `Delete/Insert/Update/Merge/Command` где угодно в `walk()`.
- Регресс-тесты `validate`; обновление `docs/architecture.md`,
  `docs/decisions.md` (ADR 13 + новый ADR про timeout).

### Этап B. Поддержка set-операций
- Разрешить корень `Union` / `Intersect` / `Except` (UNION/UNION ALL/INTERSECT/
  EXCEPT) с зажимом верхнего `LIMIT MAX_ROWS`; проверки `into`/locks/DML-дерева
  сохраняются.
- Тесты: set-операции принимаются, вложенные UNION в сабквери, мультистейтмент
  отклоняется.
- Обновление `docs/architecture.md` и `docs/decisions.md`.

### Этап C. Корректность ответа `execute_query`
- Новый формат ответа: `columns` + `rows` (массив массивов). Колонки берутся из
  `record.keys()` — порядок и дубли сохраняются. Сейчас `dict(record)` молча
  теряет колонки при `SELECT *` из JOIN с одинаковыми именами.
- `Decimal` → строка (потеря точности для numeric исчезает).
- `LIMIT ALL` (валидный PostgreSQL) — предобработка `LIMIT ALL` → большой лимит
  перед парсингом, иначе sqlglot падает с ложной ошибкой.
- Тесты; обновление `packages/db_mcp/README.md` и `docs/architecture.md`.

### Этап D. Схема для LLM: PK/FK и кэш
- В описание схемы (`schema.py`) добавить первичные и внешние ключи из
  `information_schema` (с учётом `EXCLUDED_TABLES` и маскирования PII под роль):
  `primary_key` и `foreign_keys` для каждой таблицы — улучшение генерации JOIN.
- TTL-кэш описания схемы по роли (настройка в `Settings`), чтобы `get_schema`
  не бил в БД при каждом вызове.
- Тесты `SchemaBuilder` с мок-пулом: маскирование PII (ro vs admin), PK/FK в
  выводе, кэш.
- Обновление `docs/architecture.md` и `docs/decisions.md`.

### После: приложение (packages/app)
- Конвейер text-to-SQL: генерация SQL через LLM (LangChain), валидация,
  ролевое маскирование схемы, вызов шлюза через MCP, форматирование ответа.
- REST-эндпоинты FastAPI поверх этого.
- Реальное хранилище учёток `UserCredentialsStore` на основе `db_mcp`
  (сейчас auth работает на in-memory моке).

## Текущее состояние

- База заполнена синтетикой (см. [seed.md](seed.md)).
- RLS работает: студент видит только своё, преподаватель — только свои курсы,
  администрация — всё (включая PII).
- Шлюз `db_mcp` работает как MCP-сервер на stdio: валидация SQL, исполнение
  с RLS-контекстом, маскирование схемы под роль, аудит в `query_log`
  (запросы — только SELECT, лимит строк 200).
- Auth реализован (JWT по логину/паролю, управление учётками), но хранилище
  учёток пока in-memory — подключение к `db_mcp` впереди.

## Открытые блокеры

- **Docker Hub недоступен** (TLS timeout) — используется кэшированный образ
  `postgres:16-alpine` вместо 17.