import json

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings


class OutboxEncryptionError(ValueError):
    pass


def _fernet(settings: Settings) -> Fernet:
    key = settings.outbox_encryption_key.get_secret_value()
    if not key:
        raise OutboxEncryptionError("OUTBOX_ENCRYPTION_KEY is required")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as error:
        raise OutboxEncryptionError("OUTBOX_ENCRYPTION_KEY is invalid") from error


def encrypt_template_data(data: dict[str, object], settings: Settings) -> str:
    serialized = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _fernet(settings).encrypt(serialized).decode("ascii")


def decrypt_template_data(payload: str, settings: Settings) -> dict[str, object]:
    try:
        decrypted = _fernet(settings).decrypt(payload.encode("ascii"))
        value = json.loads(decrypted)
    except (InvalidToken, UnicodeEncodeError, json.JSONDecodeError) as error:
        raise OutboxEncryptionError("Encrypted outbox payload cannot be read") from error
    if not isinstance(value, dict):
        raise OutboxEncryptionError("Encrypted outbox payload must be an object")
    return value
