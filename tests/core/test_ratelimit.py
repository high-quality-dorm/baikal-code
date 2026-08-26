"""Тесты rate limiting: скользящее окно по ключу."""

from __future__ import annotations

import pytest

from app.core.ratelimit import RateLimitExceeded, SlidingWindowLimiter


def test_allows_up_to_limit():
    limiter = SlidingWindowLimiter()
    for _ in range(3):
        limiter.check("key", limit=3, window_seconds=60)


def test_rejects_over_limit():
    limiter = SlidingWindowLimiter()
    for _ in range(3):
        limiter.check("key", limit=3, window_seconds=60)
    with pytest.raises(RateLimitExceeded):
        limiter.check("key", limit=3, window_seconds=60)


def test_keys_are_independent():
    limiter = SlidingWindowLimiter()
    for _ in range(5):
        limiter.check("a", limit=5, window_seconds=60)
    limiter.check("b", limit=5, window_seconds=60)


def test_expired_timestamps_are_pruned(monkeypatch):
    limiter = SlidingWindowLimiter()
    times = iter([0.0, 1.0, 2.0])
    monkeypatch.setattr("app.core.ratelimit.monotonic", lambda: next(times))
    limiter.check("key", limit=2, window_seconds=5)
    limiter.check("key", limit=2, window_seconds=5)
    with pytest.raises(RateLimitExceeded):
        limiter.check("key", limit=2, window_seconds=5)

    # после окна старые метки вычищаются и запрос проходит снова
    monkeypatch.setattr("app.core.ratelimit.monotonic", lambda: 10.0)
    limiter.check("key", limit=2, window_seconds=5)