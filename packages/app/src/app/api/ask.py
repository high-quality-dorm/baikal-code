"""REST-эндпоинт вопросов: POST /api/v1/ask (NDJSON-поток, гость разрешён).

Ответ — поток NDJSON-событий от тул-агента: status/query/token/done/error.
Гость работает без токена (user_id=None). Формат событий — см. ADR 36.
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.schemas import Question
from app.auth.deps import AuthContext, get_optional_context
from app.context import Context
from app.core.config import settings
from app.core.ratelimit import RateLimitExceeded

router = APIRouter(prefix="/api/v1", tags=["ask"])

OptionalUser = Annotated[AuthContext, Depends(get_optional_context)]


@router.post("/ask")
async def ask(
    question: Question, request: Request, ctx: Context, user: OptionalUser
) -> StreamingResponse:
    """Отвечает на вопрос; агент сам решает, какие тулы вызывать."""

    _check_rate_limit(ctx, request, user)

    async def gen():
        try:
            async for event in ctx.agent.stream(
                question.text, user.user_id, user.role, user.can_see_pii
            ):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except Exception as exc:  # noqa: BLE001
            yield (
                json.dumps(
                    {"type": "error", "message": f"Внутренняя ошибка: {exc}"},
                    ensure_ascii=False,
                )
                + "\n"
            )

    return StreamingResponse(gen(), media_type="application/x-ndjson")


def _check_rate_limit(ctx: Context, request: Request, user: AuthContext) -> None:
    """Проверить лимит /ask: авторизованный по user_id, гость по IP."""
    if user.user_id is not None:
        key = f"user:{user.user_id}"
        limit = settings.rate_limit_user_requests
    else:
        key = f"ip:{request.client.host if request.client else 'unknown'}"
        limit = settings.rate_limit_guest_requests
    try:
        ctx.limiter.check(key, limit, settings.rate_limit_window_seconds)
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
