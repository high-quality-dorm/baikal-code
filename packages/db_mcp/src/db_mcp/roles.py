"""Канонический вокабуляр ролей шлюза db_mcp.

Единый источник значений ролей: бизнес-роли пользователей (контракт для JWT,
`users.role` и RLS-контекста `app.role`) и роли PostgreSQL, к которым шлюз
держит пулы соединений. Приложение переиспользует `BusinessRole` вместо
собственного enum (см. этап унификации в docs/roadmap.md).
"""

from __future__ import annotations

from enum import Enum


class BusinessRole(str, Enum):
    """Бизнес-роль пользователя системы."""

    APPLICANT = "applicant"  # абитуриент
    STUDENT = "student"  # студент
    TEACHER = "teacher"  # преподаватель
    ADMIN = "admin"  # ректор, декан, сотрудники и администрация


class DbPool(Enum):
    """Роль PostgreSQL, к которой шлюз держит пул соединений."""

    RO = "ro"  # рабочая read-only роль app_ro (без PII)
    ADMIN = "admin"  # роль администрации app_admin (с PII)
    SERVICE = (
        "service"  # служебная роль app_service (аудит + auth + резолюция identity)
    )


# Значения бизнес-ролей: удобно для проверок «роль входит в набор»
BUSINESS_ROLES = frozenset(role.value for role in BusinessRole)

__all__ = ["BUSINESS_ROLES", "BusinessRole", "DbPool"]
