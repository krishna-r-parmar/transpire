from datetime import UTC, datetime, timedelta

from app.domains.tenants.reminders import cooldown_until, is_inactive

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)


def test_never_reminded_has_no_cooldown() -> None:
    assert cooldown_until(None, 72, NOW) is None


def test_recent_reminder_is_in_cooldown_until_window_ends() -> None:
    last = NOW - timedelta(hours=10)
    assert cooldown_until(last, 72, NOW) == last + timedelta(hours=72)


def test_reminder_older_than_window_is_available() -> None:
    assert cooldown_until(NOW - timedelta(hours=72), 72, NOW) is None
    assert cooldown_until(NOW - timedelta(days=5), 72, NOW) is None


def test_without_inactivity_window_everyone_is_eligible() -> None:
    assert is_inactive(NOW, None, NOW) is True
    assert is_inactive(None, None, NOW) is True


def test_never_signed_in_is_always_inactive() -> None:
    assert is_inactive(None, 30, NOW) is True


def test_inactivity_window_boundaries() -> None:
    assert is_inactive(NOW - timedelta(days=29), 30, NOW) is False
    assert is_inactive(NOW - timedelta(days=30), 30, NOW) is True
    assert is_inactive(NOW - timedelta(days=90), 30, NOW) is True
