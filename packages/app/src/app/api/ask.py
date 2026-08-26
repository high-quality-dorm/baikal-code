"""REST-эндпоинт вопросов: POST /api/v1/ask (NDJSON-поток, гость разрешён).

Ответ — поток NDJSON-событий от тул-агента: status/query/token/done/error.
Гость работает без токена (user_id=None). Формат событий — см. ADR 36.
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.schemas import Question
from app.auth.deps import AuthContext, get_optional_context
from app.context import Context

router = APIRouter(prefix="/api/v1", tags=["ask"])

OptionalUser = Annotated[AuthContext, Depends(get_optional_context)]


@router.post("/ask")
async def ask(
    question: Question, ctx: Context, user: OptionalUser
) -> StreamingResponse:
    """Отвечает на вопрос; агент сам решает, какие тулы вызывать."""

    async def gen():
        async for event in ctx.agent.stream(question.text, user.user_id, user.role):
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")
