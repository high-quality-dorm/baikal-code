"""LLM-клиент приложения: стриминговый вызов OpenAI-совместимого API."""

from app.llm.llm import ChatLLM, LLMError

__all__ = ["ChatLLM", "LLMError"]
