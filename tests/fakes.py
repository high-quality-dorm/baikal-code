"""Общие фейки тестов app: шлюз db без реальной БД.

`FakeGateway` реализует интерфейс `db.Gateway` в той части, которую использует
приложение: резолюция identity/роли, учётные записи, схема и исполнение запроса.
"""

from __future__ import annotations

from db.gateway import GatewayError
from db.models import Identity, QueryResult, SchemaDescription, UserRecord


class StubLLM:
    """Минимальный фейк LLM (для сборки контекста, где pipeline не исполняется)."""

    async def generate_sql(
        self, question: str, schema: str, role: str | None
    ) -> str:
        return "SELECT 1"

    async def answer(
        self,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[list[object]],
    ) -> str:
        return "Ответ"


def make_context(gateway: FakeGateway) -> AppContext:
    """Контекст на фейковом шлюзе: AuthService + Pipeline на заглушке LLM."""
    from app.context import AppContext
    from app.services.auth import AuthService
    from app.services.pipeline import Pipeline

    return AppContext(
        gateway=gateway,
        auth=AuthService(gateway),
        pipeline=Pipeline(gateway, StubLLM()),
    )


class FakeGateway:
    """Фейк db.Gateway: настраиваемые ответы и запись вызовов."""

    def __init__(self) -> None:
        self.users: dict[int, UserRecord] = {}
        self.by_email: dict[str, UserRecord] = {}
        self.identities: dict[int, Identity] = {}
        self.roles: dict[int, str | None] = {}
        self.schema: SchemaDescription = SchemaDescription(identity=None, tables=[])
        self.result: QueryResult = QueryResult(
            columns=[], rows=[], row_count=0, truncated=False, duration_ms=0.0
        )
        self.gateway_error: Exception | None = None
        self.get_schema_calls: list[int | None] = []
        self.execute_calls: list[tuple[str, int | None]] = []

    def add_user(
        self,
        record: UserRecord,
        *,
        identity: Identity | None = None,
        role: str | None = None,
    ) -> None:
        """Регистрирует учётку в фейке (плюс опционально identity и роль)."""
        self.users[record.id] = record
        self.by_email[record.email] = record
        if identity is not None:
            self.identities[record.id] = identity
        self.roles[record.id] = role

    async def get_user_by_login(self, login: str) -> UserRecord | None:
        return self.by_email.get(login)

    async def get_user(self, user_id: int) -> UserRecord | None:
        return self.users.get(user_id)

    async def resolve_identity(self, user_id: int) -> Identity | None:
        return self.identities.get(user_id)

    async def resolve_role(self, user_id: int) -> str | None:
        return self.roles.get(user_id)

    async def get_schema(self, user_id: int | None) -> SchemaDescription:
        self.get_schema_calls.append(user_id)
        return self.schema

    async def execute_query(self, sql: str, user_id: int | None) -> QueryResult:
        self.execute_calls.append((sql, user_id))
        if self.gateway_error is not None:
            raise self.gateway_error
        return self.result


class FailingGateway(FakeGateway):
    """Фейк, который всегда падает с GatewayError."""

    def __init__(self, message: str = "Доступ запрещён") -> None:
        super().__init__()
        self.gateway_error = GatewayError(message)