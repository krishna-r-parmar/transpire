import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()
dummy_password_hash = password_hash.hash("TRANSPIRE-dummy-credential-check")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str | None) -> bool:
    candidate_hash = encoded_hash or dummy_password_hash
    verified = password_hash.verify(password, candidate_hash)
    return bool(encoded_hash) and verified


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry(*, remember_me: bool, hours: int, remembered_days: int) -> datetime:
    duration = timedelta(days=remembered_days) if remember_me else timedelta(hours=hours)
    return datetime.now(UTC) + duration


def password_reset_expiry(minutes: int) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=minutes)
