"""Tests for clock-driven sliding window rate limiter per CONTRACT §4.4, AUTH-12."""

import pytest

from clubledger.core import clock
from clubledger.core.errors import DomainError
from clubledger.security.ratelimit import (
    check_rate_limit,
    enforce_rate_limit,
    reset_rate_limits,
)


@pytest.fixture(autouse=True)
def clean_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CLUBLEDGER_ENV", "test")
    clock.reset()
    reset_rate_limits()
    yield
    clock.reset()
    reset_rate_limits()


def test_sliding_window_rate_limiting() -> None:
    clock.set_now("2026-08-01T10:00:00Z")
    key = "login:127.0.0.1:test@example.com"
    limit = 5
    window = 60

    # 5 attempts within 60s pass
    for _ in range(5):
        assert check_rate_limit(key, limit, window) is None

    # 6th attempt within the minute fails with 429 RATE_LIMITED and retry_after
    retry_after = check_rate_limit(key, limit, window)
    assert retry_after is not None
    assert retry_after > 0

    with pytest.raises(DomainError) as exc_info:
        enforce_rate_limit(key, limit, window)
    assert exc_info.value.code == "RATE_LIMITED"
    assert exc_info.value.http_status == 429

    # Advance the injected clock by 61s: rate limit window passes, attempt is accepted again (AUTH-12)
    clock.set_now("2026-08-01T10:01:01Z")
    assert check_rate_limit(key, limit, window) is None
