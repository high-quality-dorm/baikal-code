"""REST-эндпоинт вопросов: POST /api/v1/ask (гость разрешён)."""

from __future__ import annotations

from typing import Annotated

from db.gateway import GatewayError
from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import Answer, Question
from app.auth.deps import AuthContext, get_optional_context
from app.context import Context
from app.llm import LLMError

router = APIRouter(prefix="/api/v1", tags=["ask"])

OptionalUser = Annotated[AuthContext, Depends(get_optional_context)]


@router.post("/ask", response_model=Answer)
async def ask(question: Question, ctx: Context, user: OptionalUser) -> Answer:
    """Отвечает на вопрос; гость работает без токена (user_id=None)."""
    try:
        return await ctx.pipeline.ask(question.text, user.user_id, user.role)
    except GatewayError as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка шлюза: {exc}") from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка LLM: {exc}") from exc
