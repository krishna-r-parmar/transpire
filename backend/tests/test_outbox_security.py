from cryptography.fernet import Fernet

from app.core.config import Settings
from app.domains.communications.security import (
    OutboxEncryptionError,
    decrypt_template_data,
    encrypt_template_data,
)


def _settings_with_key(key: bytes) -> Settings:
    return Settings(_env_file=None, OUTBOX_ENCRYPTION_KEY=key.decode("ascii"))


def test_sensitive_outbox_data_round_trips_without_plaintext() -> None:
    settings = _settings_with_key(Fernet.generate_key())
    data = {"action_url": "https://transpire.example/reset-password?token=secret-token"}

    encrypted = encrypt_template_data(data, settings)

    assert "secret-token" not in encrypted
    assert decrypt_template_data(encrypted, settings) == data


def test_sensitive_outbox_data_rejects_a_different_key() -> None:
    encrypted = encrypt_template_data(
        {"action_url": "https://transpire.example/reset-password?token=secret-token"},
        _settings_with_key(Fernet.generate_key()),
    )

    try:
        decrypt_template_data(encrypted, _settings_with_key(Fernet.generate_key()))
    except OutboxEncryptionError:
        pass
    else:
        raise AssertionError("A different outbox key must not decrypt the payload")


def test_sensitive_outbox_data_requires_a_key() -> None:
    settings = Settings(_env_file=None, OUTBOX_ENCRYPTION_KEY="")

    try:
        encrypt_template_data({"action_url": "https://transpire.example"}, settings)
    except OutboxEncryptionError:
        pass
    else:
        raise AssertionError("Sensitive outbox data must require an encryption key")
