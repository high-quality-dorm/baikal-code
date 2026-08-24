import jwt

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("s3cret!")
    assert hashed != "s3cret!"
    assert verify_password("s3cret!", hashed)
    assert not verify_password("wrong", hashed)


def test_create_and_decode_token():
    token = create_access_token(subject="42", role="admin", email="a@b.c")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"
    assert payload["email"] == "a@b.c"


def test_decode_raises_on_bad_token():
    try:
        decode_access_token("not-a-jwt")
        assert False, "expected error"
    except jwt.PyJWTError:
        pass
