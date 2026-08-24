"""Общие фикстуры тестов."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def gen_keypair(tmp_path: Path) -> tuple[Path, Path]:
    """Генерирует самоподписанный RSA-сертификат и закрытый ключ (для RS256)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "cert.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path = tmp_path / "key.pem"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


@pytest.fixture
def rsa_keys(tmp_path, monkeypatch):
    """Настраивает settings на свежий RSA-ключ и сбрасывает кэш настроек."""
    cert_path, key_path = gen_keypair(tmp_path)
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(key_path))
    monkeypatch.setenv("JWT_PUBLIC_KEY_PATH", str(cert_path))
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    from app.core import config as config_mod

    config_mod._settings = None
    yield
    config_mod._settings = None