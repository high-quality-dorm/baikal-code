"""Rate limiting для /ask: скользящее окно по ключу (in-process).

Лимитер — одиночка в `AppContext`: состояние живёт в памяти одного процесса
uvicorn. Ключ: для авторизованного — `user:{user_id}`, для гостя — `ip:{...}`.
Раздельные лимиты: гость строже (анонимный abuse платного LLM).

Ограничение: при нескольких worker-процессах лимит будет per-process (каждый
считает отдельно); для `make run` (один процесс) корректно. Расширение на Redis
— отдельный этап при необходимости мультипроцесса.
"""

from __future__ import annotations

from collections import deque
from time import monotonic


class RateLimitExceeded(Exception):
    """Превышен лимит запросов за окно."""


class SlidingWindowLimiter:
    """Скользящее окно запросов по ключу (устаревшие метки вычищаются)."""

    def __init__(self) -> None:
        self._timestamps: dict[str, deque[float]] = {}

    def check(self, key: str, limit: int, window_seconds: float) -> None:
        """Допустить запрос по ключу или бросить RateLimitExceeded.

        Метки старше окна удаляются при каждом обращении, поэтому память
        ограничена числом запросов за окно, а не за всё время жизни.
        """
        now = monotonic()
        timestamps = self._timestamps.setdefault(key, deque())
        while timestamps and now - timestamps[0] > window_seconds:
            timestamps.popleft()
        if len(timestamps) >= limit:
            raise RateLimitExceeded(
                f"Превышен лимит запросов: {limit} за {window_seconds:.0f} с"
            )
        timestamps.append(now)

    def prune(self) -> None:
        """Удалить ключи без активных меток (для гигиены памяти)."""
        for key, timestamps in list(self._timestamps.items()):
            if not timestamps:
                del self._timestamps[key]


__all__ = ["RateLimitExceeded", "SlidingWindowLimiter"]
