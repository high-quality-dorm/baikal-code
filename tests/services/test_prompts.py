"""Тесты системного промпта: разная формулировка PII по флагу can_see_pii."""

from __future__ import annotations

from app.agent.prompts import build_system_prompt


def _prompt(can_see_pii: bool) -> str:
    return build_system_prompt("Схема: ...", "student", can_see_pii)


def test_build_system_prompt_allows_pii_when_can_see_pii():
    prompt = _prompt(can_see_pii=True)
    assert "можно выбирать" in prompt
    assert "не выходить за этот скоуп" in prompt
    assert "только обобщения и агрегаты" not in prompt


def test_build_system_prompt_blocks_pii_for_guest():
    prompt = _prompt(can_see_pii=False)
    assert "только обобщения и агрегаты" in prompt
    assert "можно выбирать" not in prompt


def test_build_system_prompt_includes_role_and_schema():
    prompt = _prompt(can_see_pii=False)
    assert "Роль пользователя: student" in prompt
    assert "Схема базы данных:" in prompt
    assert "Схема: ..." in prompt