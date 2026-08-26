"""Резолюция identity пользователя для RLS-контекста и app-уровня.

`resolve_identity` вычисляет из `users.id` (номера учётки) два независимых
поля — `student_id` и `staff_id` — через служебную роль `app_service`.
Роль строкой не выводится здесь: скоуп RLS строит сама БД из этих id.

`resolve_role` — отдельная функция для приложения (логин, require_role): роль
выводится из наличия `student_id` (студент) или должности `staff.position`.
"""

from __future__ import annotations

from db.access import Pools
from db.models import Identity

# Должности персонала, из которых выводятся бизнес-роли
_POSITION_ROLES = frozenset({"teacher", "head", "dean", "admin"})


async def resolve_identity(pools: Pools, user_id: int | None) -> Identity | None:
    """Резолвит номер учётки в {student_id, staff_id} (или None для гостя).

    Tolerant-поведение: пустой/несуществующий user_id или неактивная учётка
    возвращают None — пользователь получает доступ как гость (RLS
    deny-by-default на students/marks, общие таблицы открыты).
    """
    if user_id is None:
        return None
    pool = await pools.service()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, student_id, staff_id, is_active FROM users WHERE id = $1",
            user_id,
        )
    if row is None or not row["is_active"]:
        return None
    return Identity(
        user_id=row["id"],
        student_id=row["student_id"],
        staff_id=row["staff_id"],
        is_active=row["is_active"],
    )


async def resolve_role(pools: Pools, user_id: int) -> str | None:
    """Бизнес-роль пользователя (для приложения): student или должность staff.

    Приоритет: известная должность (`teacher/head/dean/admin`) — выше, чем
    `student`; пользователь с обоими id представляется сотрудником. Возвращает
    None, если учётка не найдена/неактивна или должность не является известной
    бизнес-ролью (тогда студент всё ещё может остаться студентом).
    """
    pool = await pools.service()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.student_id, u.is_active, p.title AS position
              FROM users u
              LEFT JOIN staff s ON s.id = u.staff_id
              LEFT JOIN positions p ON p.id = s.position_id
             WHERE u.id = $1
            """,
            user_id,
        )
    if row is None or not row["is_active"]:
        return None
    position = row["position"]
    if position in _POSITION_ROLES:
        return position
    if row["student_id"] is not None:
        return "student"
    return None
