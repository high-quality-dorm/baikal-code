"""Хеширование паролей и работа с JWT-токенами."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from .config import get_settings


def hash_password(plain: str) -> str:
    """Возвращает bcrypt-хэш пароля."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Проверяет пароль против bcrypt-хэша."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str, role: str, email: str | None = None) -> str:
    """Создаёт JWT access-токен с ролью и внутренним id."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expires_minutes),
    }
    if email is not None:
        payload["email"] = email
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Декодирует JWT; при невалидном/просроченном токене бросает jwt.PyJWTError."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
