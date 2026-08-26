# db

Пакет работы с базой данных университета. Единственный шлюз к PostgreSQL:
приложение не ходит в БД напрямую — только через фасад `db.gateway.Gateway`.

## Модель доступа (set-based)

Роль строкой не хранится и не передаётся. Доступ выводится из двух независимых
id пользователя — `student_id` и `staff_id` (см. [docs/roles.md](../../docs/roles.md)):

- RLS-контекст задаётся GUC `app.student_id`/`app.staff_id`;
- гость (нет user_id или нет id) видит только общие таблицы;
- скоупы зав.кафедрой/декана/администрации выводятся из `staff.position`.

## Модули

- `access.py` — пулы соединений asyncpg (роли `app_ro` / `app_service`) и
  установка RLS-контекста в начале транзакции; создание пула сериализуется
  локом; в транзакции ставится `statement_timeout` (10 с по умолчанию).
- `identity.py` — резолюция identity: `users.id` → `Identity(student_id,
  staff_id, is_active)` через роль `app_service`; `resolve_role` — для
  app-уровня (student или должность из `staff.position`).
- `validate.py` — валидация SQL (sqlglot): только один read-only запрос
  (SELECT или UNION/INTERSECT/EXCEPT), запрет опасных функций, DML в любом
  узле дерева, FOR UPDATE/FOR SHARE, лимит строк (`MAX_ROWS = 200`);
  `LIMIT ALL` принимается и зажимается до лимита.
- `schema.py` — маскированное описание схемы для LLM из каталога БД + русские
  описания таблиц и колонок; гость не видит `students`/`marks`; PK/FK для
  генерации JOIN — из статического `TABLE_META`.
- `audit.py` — запись запросов в `query_log` через роль `app_service`.
- `userstore.py` — чтение/запись учётных записей (`users`) для auth через роль
  `app_service`.
- `models.py` — pydantic-модели контракта: `Identity`, `QueryResult`,
  `SchemaDescription`, `TableInfo`, `ColumnInfo`, `UserRecord`.
- `gateway.py` — фасад `Gateway` (единая точка входа для приложения).

## Фасад Gateway

- `get_schema(user_id)` — описание схемы, маскированное под пользователя.
- `execute_query(sql, user_id)` — валидация → резолюция identity → исполнение
  с RLS → аудит. `user_id` — **номер учётки** (`users.id`, `sub` из JWT) или
  None для гостя; роль не передаётся — скоуп выводит БД. Ответ —
  `QueryResult {columns, rows, row_count, truncated, duration_ms}` (rows —
  массив массивов, дубли колонок сохраняются; numeric — строкой без потери
  точности).
- `resolve_identity` / `resolve_role` — для приложения (логин, require_role).
- CRUD учёток: `get_user_by_login`, `get_user`, `list_users`, `create_user`,
  `update_user`, `deactivate_user`, `has_admin`.

Подробнее — в [docs/architecture.md](../../docs/architecture.md) и
[docs/roles.md](../../docs/roles.md).