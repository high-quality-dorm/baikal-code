"""Тесты системного промпта: PII по флагу can_see_pii, скоуп доступа по роли."""

from __future__ import annotations

import pytest

from app.agent.prompts import _ROLE_ACCESS, build_system_prompt


def _prompt(can_see_pii: bool = False, role: str | None = "student") -> str:
    return build_system_prompt("Схема: ...", role, can_see_pii)


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


def test_build_system_prompt_mentions_role_read_restriction():
    prompt = _prompt()
    assert "Доступ к данным ограничен ролью пользователя" in prompt
    assert "не пытайся обойти права" in prompt


def test_build_system_prompt_guides_general_stats_through_views():
    prompt = _prompt()
    assert "вью v_students_*" in prompt
    assert "напрямую из students" in prompt


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (None, "Гость: общая информация"),
        ("guest", "Гость: общая информация"),
        ("student", "Студент: собственная строка в students"),
        ("teacher", "Преподаватель: студенты групп своих занятий"),
        ("head", "Зав. кафедрой: студенты групп, посещающих занятия"),
        ("dean", "Декан: студенты своего факультета"),
        ("admin", "Администрация: все студенты"),
    ],
)
def test_build_system_prompt_role_access_scope(role, expected):
    prompt = _prompt(role=role)
    assert expected in prompt


def test_build_system_prompt_unknown_role_falls_back_to_guest():
    prompt = _prompt(role="unknown_role")
    assert "Гость: общая информация" in prompt
    assert _ROLE_ACCESS["guest"] in prompt