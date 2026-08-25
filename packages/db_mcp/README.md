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
  (10 с по умолчанию).
- `validate.py` — валидация SQL (sqlglot): только один read-only SELECT,
  запрет опасных функций, лимит строк (`MAX_ROWS = 200`).
- `schema.py` — маскированное описание схемы для LLM из каталога БД + русские
  описания таблиц и колонок.
- `audit.py` — запись запросов в `query_log` через роль `app_audit`.
- `server.py` — MCP-сервер (mcp 2.0, `MCPServer`) на stdio.

## Запуск

```bash
uv run db-mcp   # MCP-сервер на stdio (см. db-mcp = "db_mcp.server:main")
```

## Инструменты MCP

- `get_schema(role)` — описание схемы, маскированное под роль.
- `execute_query(sql, role, user_id)` — валидация → исполнение с RLS → аудит.

Подробнее — в [docs/architecture.md](../../docs/architecture.md) и
[docs/roles.md](../../docs/roles.md).