"""Валидация SQL перед исполнением.

Гарантирует, что шлюз исполняет только безопасные read-only запросы:

- ровно одно выражение (без мультистейтментов);
- корень выражения — SELECT или set-операция (UNION/INTERSECT/EXCEPT);
  DDL/DML/COPY/SET и прочее отклоняется;
- запрет SELECT INTO;
- запрет изменяющих операций в любом узле дерева (DML в WITH/подзапросах);
- запрет клаузы блокировки строк (FOR UPDATE / FOR SHARE);
- запрет вызова опасных функций (pg_sleep, pg_read_file, nextval и т.п.);
- гарантированный лимит строк (LIMIT), чтобы один запрос не выгружал всю базу.

Разбор выполняется sqlglot с диалектом PostgreSQL: он корректно обрабатывает
комментарии, кавычки, WITH-выражения и нормализует SQL перед исполнением.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import sqlglot
import sqlglot.expressions as exp
from sqlglot.errors import ParseError

# Максимум строк, возвращаемых одним запросом
MAX_ROWS = 200

# Валидный PostgreSQL `LIMIT ALL` (безлимит) sqlglot не разбирает.
# Используется как fallback только при ошибке парсинга: `LIMIT ALL`
# заменяется на большой лимит, который после проверки зажмётся до MAX_ROWS.
_LIMIT_ALL_RE = re.compile(r"\bLIMIT\s+ALL\b", re.IGNORECASE)

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
        # последовательности (мутируют состояние БД)
        "nextval",
        "currval",
        "setval",
        # большие объекты: операции записи/чтения по дескриптору
        "lo_open",
        "lo_close",
        "lo_unlink",
        "lo_put",
        "lo_truncate",
        # advisory locks и уведомления
        "pg_advisory_lock",
        "pg_advisory_unlock",
        "pg_advisory_unlock_all",
        "pg_advisory_xact_lock",
        "pg_try_advisory_lock",
        "pg_try_advisory_xact_lock",
        "pg_advisory_lock_shared",
        "pg_advisory_unlock_shared",
        "pg_try_advisory_lock_shared",
        "pg_try_advisory_xact_lock_shared",
        "pg_notify",
        # снапшоты (нарушают изоляцию / дают доступ к чужим состояниям)
        "pg_export_snapshot",
        "pg_import_snapshot",
        # прочее опасное
        "pg_logdir_ls",
        "inet_server_addr",
        "inet_client_addr",
        "pg_backend_pid",
        "current_setting",
        "set_config",
    }
)


# Изменяющие данные операции. Запрещены даже внутри WITH/подзапросов:
# `WITH del AS (DELETE ... RETURNING *) SELECT * FROM del` имеет корень Select,
# но выполняет DML — такие запросы отсекаются на уровне валидации, а не только
# грантами БД.
_MUTATING_NODES = (
    exp.Delete,
    exp.Insert,
    exp.Update,
    exp.Merge,
    exp.Command,
    exp.Copy,
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


def _existing_limit(tree: exp.Expression) -> int | None:
    """Числовое значение LIMIT, если оно задано простым литералом.

    Работает и для SELECT, и для set-операций (UNION/INTERSECT/EXCEPT):
    у корневого узла LIMIT хранится в `args["limit"]`.
    """
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


def _check_read_only_tree(tree: exp.Expression) -> None:
    """Отклонить запрос, содержащий изменяющие данные операции.

    Корень может быть SELECT, но DML может прятаться в WITH-выражениях или
    подзапросах (например, `WITH del AS (DELETE ... RETURNING *) SELECT *`
    из del). Ходим по всему дереву и отсекаем мутирующие узлы.
    """
    for node in tree.walk():
        if isinstance(node, _MUTATING_NODES):
            raise ValidationError("Запрос должен быть read-only (SELECT)")


def _check_no_locks(tree: exp.Expression) -> None:
    """Отклонить SELECT с клаузой блокировки строк (FOR UPDATE/FOR SHARE)."""
    for node in tree.walk():
        if isinstance(node, exp.Select) and node.args.get("locks"):
            raise ValidationError("FOR UPDATE / FOR SHARE запрещены")


def _check_no_into(tree: exp.Expression) -> None:
    """Отклонить SELECT INTO в любом узле.

    У set-операций `SELECT * INTO t FROM a UNION SELECT * FROM b` клауза INTO
    лежит на первом операнде (Select), поэтому проверяем по всему дереву,
    а не только на корне.
    """
    for node in tree.walk():
        if isinstance(node, exp.Select) and node.args.get("into") is not None:
            raise ValidationError("SELECT INTO запрещён")


def validate(sql: str) -> ValidatedQuery:
    """Проверить SQL и вернуть нормализованный безопасный запрос.

    Допустим единственный read-only запрос: SELECT или set-операция
    (UNION/INTERSECT/EXCEPT). Верхний LIMIT зажимается до MAX_ROWS.

    Raises:
        ValidationError: если SQL не является read-only запросом.
    """
    if not sql or not sql.strip():
        raise ValidationError("SQL не должен быть пустым")

    try:
        statements = sqlglot.parse(sql, read="postgres")
    except ParseError as exc:
        # `LIMIT ALL` — валидный PostgreSQL, но sqlglot его не разбирает.
        # Fallback срабатывает только при ошибке парсинга: запросы, где
        # «LIMIT ALL» встречается в строковых литералах или комментариях,
        # парсятся штатно и не затрагиваются.
        if not _LIMIT_ALL_RE.search(sql):
            raise ValidationError(f"Не удалось разобрать SQL: {exc}") from exc
        fixed = _LIMIT_ALL_RE.sub(f"LIMIT {MAX_ROWS + 1}", sql)
        statements = sqlglot.parse(fixed, read="postgres")

    # Отбрасываем служебные узлы (завершающие точки с запятой)
    statements = [
        s for s in statements if s is not None and not isinstance(s, exp.Semicolon)
    ]
    if not statements:
        raise ValidationError("SQL не содержит выражений")
    if len(statements) > 1:
        raise ValidationError("Разрешён только один SQL-запрос")

    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.SetOperation)):
        raise ValidationError(
            "Разрешены только read-only запросы (SELECT, UNION/INTERSECT/EXCEPT)"
        )
    _check_no_into(tree)
    _check_read_only_tree(tree)
    _check_no_locks(tree)
    _check_forbidden_functions(tree)

    limit = _existing_limit(tree)
    limit_applied = False
    if limit is None or limit > MAX_ROWS:
        tree = tree.limit(MAX_ROWS)
        limit_applied = True

    return ValidatedQuery(sql=tree.sql(dialect="postgres"), limit_applied=limit_applied)
