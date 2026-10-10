"""Turn stored UTC event timestamps into readable Indian campus times.

This module only formats display values; it never changes event eligibility,
prices, reservation expiry or database timestamps.
"""

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def event_date(value: str) -> str:
    """Show the event's calendar date in IST, retaining invalid input safely."""
    try:
        return _local_time(value).strftime("%d %b %Y").lstrip("0")
    except (ValueError, TypeError):
        return str(value)


def event_time(value: str) -> str:
    """Show a readable clock time with an explicit timezone label."""
    try:
        return _local_time(value).strftime("%I:%M %p IST").lstrip("0")
    except (ValueError, TypeError):
        return str(value)


def _local_time(value: str) -> datetime:
    """Convert a stored UTC timestamp without mutating the stored value."""
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(IST)
