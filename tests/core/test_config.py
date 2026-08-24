import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_settings_defaults():
    settings = get_settings()
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_expires_minutes > 0
    assert len(settings.jwt_secret.encode()) >= 32


def test_settings_accepts_long_secret():
    settings = Settings(jwt_secret="x" * 32)
    assert len(settings.jwt_secret) == 32


def test_settings_rejects_short_secret():
    with pytest.raises(ValidationError):
        Settings(jwt_secret="short")
