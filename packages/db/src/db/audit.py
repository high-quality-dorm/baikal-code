"""Аудит запросов: запись в query_log.

Запись выполняется через служебную роль app_service (права только на
query_log для аудита и на users для auth), чтобы шлюз логировал запросы даже
для ролей без прав на служебные таблицы. question пока не передаётся (только
SQL) — сессионные контексты пользователей будут добавлены позже.

Сбой аудита не должен ронять основной запрос: ошибка логируется и
проглатывается.
"""

from __future__ import annotations

import logging

from db.access import Pools

logger = logging.getLogger(__name__)

_INSERT_SQL = """
    INSERT INTO query_log (role, user_id, sql_query, status, row_count, error, duration_ms)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
"""


class Auditor:
    """Пишет записи в query_log через пул роли app_service."""

    def __init__(self, pools: Pools) -> None:
        self._pools = pools

    async def record(
        self,
        *,
        role: str | None,
        user_id: str | None,
        sql_query: str,
        status: str,
        row_count: int | None = None,
        error: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Сохранить запись о выполненном запросе."""
        try:
            pool = await self._pools.service()
            async with pool.acquire() as conn:
                await conn.execute(
                    _INSERT_SQL,
                    role,
                    user_id,
                    sql_query,
                    status,
                    row_count,
                    error,
                    duration_ms,
                )
        except Exception:
            logger.exception("Не удалось записать запрос в query_log")
