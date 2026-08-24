import pytest

from app.core.config import Settings, get_settings


def test_settings_defaults():
    settings = get_settings()
    assert settings.jwt_algorithm == "RS256"
    assert settings.jwt_expires_minutes > 0
    assert settings.jwt_private_key_path == "certs/jwt-private-key.pem"
    assert settings.jwt_public_key_path == "certs/jwt-cert.pem"


def test_settings_accepts_custom_paths():
    settings = Settings(
        jwt_private_key_path="/tmp/private.pem",
        jwt_public_key_path="/tmp/public.pem",
    )
    assert settings.jwt_private_key_path == "/tmp/private.pem"
    assert settings.jwt_public_key_path == "/tmp/public.pem"


def test_settings_rejects_no_secret_field():
    settings = Settings()
    assert not hasattr(settings, "jwt_secret")