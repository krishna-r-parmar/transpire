"""Encrypt small secrets (such as SFTP credentials) at rest with the platform Fernet key."""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings


class SecretError(ValueError):
    pass


def _fernet(settings: Settings) -> Fernet:
    key = settings.outbox_encryption_key.get_secret_value()
    if not key:
        raise SecretError("OUTBOX_ENCRYPTION_KEY is required to store credentials")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as error:
        raise SecretError("OUTBOX_ENCRYPTION_KEY is invalid") from error


def encrypt_secret(value: str, settings: Settings) -> str:
    return _fernet(settings).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(payload: str, settings: Settings) -> str:
    try:
        return _fernet(settings).decrypt(payload.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeEncodeError, UnicodeDecodeError) as error:
        raise SecretError("Stored credential cannot be read") from error
