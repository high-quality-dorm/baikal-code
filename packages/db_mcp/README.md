# db_mcp

Единственный шлюз доступа к базе данных университета. Приложение не ходит в
PostgreSQL напрямую — только через этот пакет, где сосредоточены безопасность,
валидация, ролевое маскирование схемы и аудит.

## Модули

- `roles.py` — канонический вокабуляр ролей: `BusinessRole`
  (applicant/student/teacher/admin) и `DbPool` (ro/admin/audit).
- `access.py` — пулы соединений asyncpg по ролям PostgreSQL и установка
  RLS-контекста (`app.role` / `app.user_id`) в начале транзакции; создание
  пула сериализуется локом; в транзакции ставится `statement_timeout`
  (10 с по умолчанию); **резолюция identity**: `user_id` (номер учётки,
  `users.id`) резолвится в доменный `internal_id` через роль `app_audit`
  и ставится как `app.user_id` для RLS.
- `validate.py` — валидация SQL (sqlglot): только один read-only запрос
  (SELECT или UNION/INTERSECT/EXCEPT), запрет опасных функций, DML в любом
  узле дерева, FOR UPDATE/FOR SHARE, лимит строк (`MAX_ROWS = 200`);
  `LIMIT ALL` принимается и зажимается до лимита.
- `schema.py` — маскированное описание схемы для LLM из каталога БД + русские
  описания таблиц и колонок; PK/FK для генерации JOIN — из статического
  `TABLE_META`.
- `audit.py` — запись запросов в `query_log` через роль `app_audit`.
- `server.py` — MCP-сервер (mcp 2.0, `MCPServer`) на stdio.

## Запуск

```bash
uv run db-mcp   # MCP-сервер на stdio (см. db-mcp = "db_mcp.server:main")
```

## Инструменты MCP

- `get_schema(role)` — описание схемы, маскированное под роль.
- `execute_query(sql, role, user_id)` — валидация → резолюция identity →
  исполнение с RLS → аудит. `user_id` здесь — **номер учётки** (`users.id`,
  `sub` из JWT), а не доменный ID: резолюцию в `internal_id` выполняет сам
  шлюз. В `query_log.user_id` пишется `users.id`.
  Ответ: `{columns, rows, row_count, truncated, duration_ms}` (rows — массив
  массивов, дубли колонок сохраняются; numeric — строкой без потери точности).

Подробнее — в [docs/architecture.md](../../docs/architecture.md) и
[docs/roles.md](../../docs/roles.md).