"""REST-эндпоинт вопросов: POST /api/v1/ask."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import Answer, Question
from app.auth.deps import AuthContext, get_current_user
from app.gateway import GatewayError
from app.llm import LLMError
from app.services.pipeline import Pipeline

router = APIRouter(prefix="/api/v1", tags=["ask"])


def _pipeline_dep() -> Pipeline:
    """Возвращает конвейер; переопределяется в create_app для общего инстанса."""
    raise NotImplementedError


PipelineDep = Annotated[Pipeline, Depends(_pipeline_dep)]
CurrentUser = Annotated[AuthContext, Depends(get_current_user)]


@router.post("/ask", response_model=Answer)
async def ask(question: Question, ctx: CurrentUser, pipeline: PipelineDep) -> Answer:
    """Отвечает на вопрос пользователя; контекст доступа — роль и users.id из JWT."""
    role = ctx.role or ""
    user_id = ctx.user_id or ""
    try:
        return await pipeline.ask(question.text, role, user_id)
    except GatewayError as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка шлюза: {exc}") from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка LLM: {exc}") from exc
