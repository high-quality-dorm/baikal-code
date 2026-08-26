"""Хеширование паролей и работа с JWT-токенами (подпись RSA/RS256)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import bcrypt
import jwt
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from .config import settings


def _load_private_key(path: str) -> rsa.RSAPrivateKey:
    """Загружает закрытый ключ; при отсутствии файла — понятная ошибка."""
    key_path = Path(path)
    if not key_path.exists():
        raise RuntimeError(
            f"Закрытый ключ для подписи JWT не найден: {key_path}. "
            "Сгенерируйте его: make certs"
        )
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise TypeError(
            f"Ключ {key_path} не является RSA-ключом; ожидаются ключи из `make certs`"
        )
    return key


def _load_public_key(path: str) -> rsa.RSAPublicKey:
    """Загружает публичный ключ из сертификата; при отсутствии — понятная ошибка."""
    cert_path = Path(path)
    if not cert_path.exists():
        raise RuntimeError(
            f"Сертификат для проверки JWT не найден: {cert_path}. "
            "Сгенерируйте его: make certs"
        )
    public_key = x509.load_pem_x509_certificate(cert_path.read_bytes()).public_key()
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise TypeError(
            f"Сертификат {cert_path} не содержит RSA-ключ; "
            "ожидается сертификат из `make certs`"
        )
    return public_key


@lru_cache(maxsize=8)
def _private_key(path: str) -> rsa.RSAPrivateKey:
    return _load_private_key(path)


@lru_cache(maxsize=8)
def _public_key(path: str) -> rsa.RSAPublicKey:
    return _load_public_key(path)


def hash_password(plain: str) -> str:
    """Возвращает bcrypt-хэш пароля."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Проверяет пароль против bcrypt-хэша."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str) -> str:
    """Создаёт JWT access-токен (RS256), подписанный закрытым ключом.

    Роль в токен не кладётся: она резолвится на каждый запрос через пакет db.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expires_minutes),
    }
    key = _private_key(settings.jwt_private_key_path)
    return jwt.encode(payload, key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Декодирует JWT по публичному ключу из сертификата.

    При невалидном/просроченном токене бросает jwt.PyJWTError.
    """
    key = _public_key(settings.jwt_public_key_path)
    return jwt.decode(token, key, algorithms=[settings.jwt_algorithm])
