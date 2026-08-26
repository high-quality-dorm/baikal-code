import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from tests.conftest import gen_keypair


def test_password_hash_roundtrip():
    hashed = hash_password("s3cret!")
    assert hashed != "s3cret!"
    assert verify_password("s3cret!", hashed)
    assert not verify_password("wrong", hashed)


def test_create_and_decode_token(rsa_keys):
    token = create_access_token(subject="42")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    # Роль не кладётся в токен: она резолвится на каждый запрос через db.
    assert "role" not in payload


def test_decode_raises_on_bad_token(rsa_keys):
    with pytest.raises(jwt.PyJWTError):
        decode_access_token("not-a-jwt")


def test_decode_rejects_token_signed_with_other_key(tmp_path, monkeypatch):
    from app.core import security as security_mod
    from app.core.config import Settings

    cert_path, key_path = gen_keypair(tmp_path)
    monkeypatch.setattr(
        security_mod,
        "settings",
        Settings(
            jwt_algorithm="RS256",
            jwt_private_key_path=str(key_path),
            jwt_public_key_path=str(cert_path),
        ),
    )
    token = create_access_token(subject="42")

    other_cert, _ = gen_keypair(tmp_path / "other")
    monkeypatch.setattr(
        security_mod,
        "settings",
        Settings(
            jwt_algorithm="RS256",
            jwt_private_key_path=str(key_path),
            jwt_public_key_path=str(other_cert),
        ),
    )
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)


def test_create_token_raises_when_key_missing(tmp_path, monkeypatch):
    from app.core import security as security_mod
    from app.core.config import Settings

    monkeypatch.setattr(
        security_mod,
        "settings",
        Settings(
            jwt_algorithm="RS256",
            jwt_private_key_path=str(tmp_path / "missing-key.pem"),
            jwt_public_key_path=str(tmp_path / "missing-cert.pem"),
        ),
    )
    with pytest.raises(RuntimeError, match="make certs"):
        create_access_token(subject="42")