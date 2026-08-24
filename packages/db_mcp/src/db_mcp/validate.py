"""Валидация SQL перед исполнением.

Гарантирует, что шлюз исполняет только безопасные read-only запросы:

- ровно одно выражение (без мультистейтментов);
- корень выражения — только SELECT (DDL/DML/COPY/SET и прочее отклоняется);
- запрет SELECT INTO;
- запрет вызова опасных функций (pg_sleep, pg_read_file и т.п.);
- гарантированный лимит строк (LIMIT), чтобы один запрос не выгружал всю базу.

Разбор выполняется sqlglot с диалектом PostgreSQL: он корректно обрабатывает
комментарии, кавычки, WITH-выражения и нормализует SQL перед исполнением.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
import sqlglot.expressions as exp
from sqlglot.errors import ParseError

# Максимум строк, возвращаемых одним запросом
MAX_ROWS = 200

# Функции, вызов которых запрещён даже внутри read-only SELECT
FORBIDDEN_FUNCTIONS = frozenset(
    {
        # системные/административные
        "pg_sleep",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
        "pg_rotate_logfile",
        # чтение/запись файлов и каталогов
        "pg_read_file",
        "pg_read_binary_file",
        "pg_write_file",
        "pg_ls_dir",
        "pg_ls_logdir",
        "pg_ls_waldir",
        "pg_stat_file",
        "pg_read_file_meta",
        # большие объекты / внешние подключения
        "lo_import",
        "lo_export",
        "lo_creat",
        "lo_create",
        "dblink",
        "dblink_connect",
        # прочее опасное
        "pg_logdir_ls",
        "inet_server_addr",
        "inet_client_addr",
        "pg_backend_pid",
        "current_setting",
        "set_config",
    }
)


class ValidationError(ValueError):
    """SQL не прошёл валидацию шлюза."""


@dataclass(frozen=True)
class ValidatedQuery:
    """Результат валидации: нормализованный SQL и признак применения лимита."""

    sql: str
    limit_applied: bool


def _func_name(node: exp.Func) -> str | None:
    """Имя вызываемой функции (для Anonymous хранится в .name)."""
    if isinstance(node, exp.Anonymous):
        return node.name
    return node.sql_name()


def _existing_limit(tree: exp.Select) -> int | None:
    """Числовое значение LIMIT, если оно задано простым литералом."""
    limit = tree.args.get("limit")
    if limit is None:
        return None
    expr = limit.expression
    if isinstance(expr, exp.Literal):
        try:
            return int(expr.this)
        except (TypeError, ValueError):
            return None
    return None


def _check_forbidden_functions(tree: exp.Expression) -> None:
    """Отклонить SELECT, вызывающий запрещённые функции."""
    for node in tree.walk():
        if not isinstance(node, exp.Func):
            continue
        name = _func_name(node)
        if name and name.lower() in FORBIDDEN_FUNCTIONS:
            raise ValidationError(f"Функция {name} запрещена")


def validate(sql: str) -> ValidatedQuery:
    """Проверить SQL и вернуть нормализованный безопасный запрос.

    Raises:
        ValidationError: если SQL не является единственным read-only SELECT.
    """
    if not sql or not sql.strip():
        raise ValidationError("SQL не должен быть пустым")

    try:
        statements = sqlglot.parse(sql, read="postgres")
    except ParseError as exc:
        raise ValidationError(f"Не удалось разобрать SQL: {exc}") from exc

    # Отбрасываем служебные узлы (завершающие точки с запятой)
    statements = [
        s for s in statements if s is not None and not isinstance(s, exp.Semicolon)
    ]
    if not statements:
        raise ValidationError("SQL не содержит выражений")
    if len(statements) > 1:
        raise ValidationError("Разрешён только один SQL-запрос")

    tree = statements[0]
    if not isinstance(tree, exp.Select):
        raise ValidationError("Разрешены только SELECT-запросы")
    if tree.args.get("into") is not None:
        raise ValidationError("SELECT INTO запрещён")
    _check_forbidden_functions(tree)

    limit = _existing_limit(tree)
    limit_applied = False
    if limit is None or limit > MAX_ROWS:
        tree = tree.limit(MAX_ROWS)
        limit_applied = True

    return ValidatedQuery(sql=tree.sql(dialect="postgres"), limit_applied=limit_applied)
