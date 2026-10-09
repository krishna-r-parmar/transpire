from datetime import UTC, datetime

from app.domains.identity.services import (
    generate_session_token,
    hash_password,
    hash_session_token,
    password_reset_expiry,
    session_expiry,
    verify_password,
)


def test_password_hash_round_trip_and_rejects_wrong_password() -> None:
    encoded = hash_password("A-long-development-password")

    assert encoded != "A-long-development-password"
    assert verify_password("A-long-development-password", encoded)
    assert not verify_password("not-the-password", encoded)
    assert not verify_password("not-the-password", None)


def test_session_tokens_are_opaque_and_hash_deterministically() -> None:
    first = generate_session_token()
    second = generate_session_token()

    assert first != second
    assert len(first) >= 64
    assert hash_session_token(first) == hash_session_token(first)
    assert first not in hash_session_token(first)


def test_remembered_session_outlives_standard_session() -> None:
    now = datetime.now(UTC)
    standard = session_expiry(remember_me=False, hours=12, remembered_days=30)
    remembered = session_expiry(remember_me=True, hours=12, remembered_days=30)

    assert standard > now
    assert remembered > standard


def test_password_reset_expiry_uses_configured_minutes() -> None:
    now = datetime.now(UTC)
    expiry = password_reset_expiry(30)

    assert expiry > now
    assert 29 * 60 < (expiry - now).total_seconds() <= 30 * 60 + 1
