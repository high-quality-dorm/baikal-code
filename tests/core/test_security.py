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
    token = create_access_token(subject="42", role="admin", email="a@b.c")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"
    assert payload["email"] == "a@b.c"


def test_decode_raises_on_bad_token(rsa_keys):
    with pytest.raises(jwt.PyJWTError):
        decode_access_token("not-a-jwt")


def test_decode_rejects_token_signed_with_other_key(tmp_path, monkeypatch):
    from app.core import config as config_mod

    cert_path, key_path = gen_keypair(tmp_path)
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(key_path))
    monkeypatch.setenv("JWT_PUBLIC_KEY_PATH", str(cert_path))
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    config_mod._settings = None
    token = create_access_token(subject="42", role="admin")
    config_mod._settings = None

    other_cert, _ = gen_keypair(tmp_path / "other")
    monkeypatch.setenv("JWT_PUBLIC_KEY_PATH", str(other_cert))
    config_mod._settings = None
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)


def test_create_token_raises_when_key_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(tmp_path / "missing-key.pem"))
    monkeypatch.setenv("JWT_PUBLIC_KEY_PATH", str(tmp_path / "missing-cert.pem"))
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    from app.core import config as config_mod

    config_mod._settings = None
    with pytest.raises(RuntimeError, match="make certs"):
        create_access_token(subject="42", role="admin")