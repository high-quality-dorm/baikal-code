"""Рендер описания схемы (SchemaDescription) в текст для LLM-промпта.

Маскирование (гость vs аутентифицированный) уже выполнено пакетом db: здесь —
только человекочитаемое представление: идентичность пользователя (чтобы LLM
мог скоупить запрос на свои id), таблицы с колонками (тип, описание, метка
PII), первичные и внешние ключи.
"""

from __future__ import annotations

from db.models import SchemaDescription


def schema_to_text(schema: SchemaDescription) -> str:
    """Читаемое текстовое описание схемы для генерации SQL."""
    lines: list[str] = []
    if schema.identity is not None:
        identity = schema.identity
        lines.append(
            "Идентичность пользователя: "
            f"user_id={identity.user_id}, "
            f"student_id={identity.student_id}, "
            f"staff_id={identity.staff_id}"
        )
    else:
        lines.append(
            "Пользователь: гость (персональные данные студентов и успеваемость "
            "недоступны)."
        )
    lines.append("")
    for table in schema.tables:
        header = f"Таблица {table.name}"
        if table.title:
            header += f" — {table.title}"
        lines.append(header)
        if table.description:
            lines.append(f"  {table.description}")
        if table.primary_key:
            lines.append(f"  PK: {', '.join(table.primary_key)}")
        for fk in table.foreign_keys:
            lines.append(
                f"  FK: {fk.column} -> {fk.references_table}.{fk.references_column}"
            )
        for col in table.columns:
            nullable = "null" if col.nullable else "not null"
            note = " [PII]" if col.sensitive else ""
            desc = f" — {col.description}" if col.description else ""
            lines.append(f"  {col.name} {col.type} {nullable}{note}{desc}")
        lines.append("")
    return "\n".join(lines).strip()
