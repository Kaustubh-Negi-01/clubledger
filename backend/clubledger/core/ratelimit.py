# In plain English: Limits repeated requests such as login attempts and invalid webhooks.
"""In-process rate limiting keyed on deterministic clock per CONTRACT §4.4, AUTH-12."""

from datetime import datetime, timezone
from typing import Dict, List

from clubledger.core import clock
from clubledger.core.errors import DomainError


# In-memory storage for sliding window timestamps
_buckets: Dict[str, List[datetime]] = {}


def _get_current_dt() -> datetime:
    iso = clock.now()
    if iso.endswith("Z"):
        return datetime.fromisoformat(iso[:-1]).replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


def check_rate_limit(key: str, limit: int, window_seconds: int) -> int | None:
    """Check and record a rate limit attempt.

    Returns None if request is within limit, or retry_after seconds if rate-limited.
    """
    now_dt = _get_current_dt()
    timestamps = _buckets.get(key, [])

    # Retain only timestamps within the window
    cutoff = now_dt.timestamp() - window_seconds
    valid_timestamps = [ts for ts in timestamps if ts.timestamp() > cutoff]

    if len(valid_timestamps) >= limit:
        # Rate limit exceeded. Compute retry_after based on the oldest timestamp in window
        oldest_ts = valid_timestamps[0].timestamp()
        retry_after = max(1, int(oldest_ts + window_seconds - now_dt.timestamp()))
        _buckets[key] = valid_timestamps
        return retry_after

    valid_timestamps.append(now_dt)
    _buckets[key] = valid_timestamps
    return None


def enforce_rate_limit(key: str, limit: int, window_seconds: int) -> None:
    """Check rate limit and raise DomainError('RATE_LIMITED', 429) if exceeded."""
    retry_after = check_rate_limit(key, limit, window_seconds)
    if retry_after is not None:
        error = DomainError(
            "RATE_LIMITED",
            http_status=429,
            message=f"Rate limit exceeded. Try again in {retry_after} seconds.",
        )
        error.retry_after = retry_after
        raise error


def reset_rate_limits() -> None:
    """Reset all in-memory rate limit buckets (useful for test fixtures)."""
    global _buckets
    _buckets.clear()
