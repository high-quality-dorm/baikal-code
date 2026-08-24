from app.core.config import get_settings


def test_settings_defaults():
    settings = get_settings()
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_expires_minutes > 0
