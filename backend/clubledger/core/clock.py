# In plain English: Provides one clock for production, development demonstrations and tests.
"""Deterministic clock module per CONTRACT.md G4, G9, §13.3."""

from datetime import datetime, timezone, timedelta
import os
from typing import Union

_IST = timezone(timedelta(hours=5, minutes=30))
_override_now: str | None = None


def now() -> str:
    """Return the current UTC timestamp formatted as YYYY-MM-DDTHH:MM:SSZ."""
    if _override_now is not None:
        return _override_now
    if os.environ.get("CLUBLEDGER_ENV", "dev") == "dev" and os.environ.get(
        "CLUBLEDGER_DEMO_TIME"
    ):
        return os.environ["CLUBLEDGER_DEMO_TIME"]
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def set_now(dt: Union[str, datetime]) -> None:
    """Inject a deterministic timestamp.

    Raises RuntimeError unless CLUBLEDGER_ENV == 'test'.
    """
    env = os.environ.get("CLUBLEDGER_ENV", "dev").lower()
    if env != "test":
        raise RuntimeError(
            f"set_now() is allowed only when CLUBLEDGER_ENV == 'test', but got '{env}'"
        )

    global _override_now
    if isinstance(dt, str):
        # Validate format
        if dt.endswith("Z"):
            parsed = datetime.fromisoformat(dt[:-1]).replace(tzinfo=timezone.utc)
        else:
            parsed = datetime.fromisoformat(dt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
        _override_now = parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
    elif isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        _override_now = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        raise TypeError(f"dt must be str or datetime, got {type(dt)}")


def reset() -> None:
    """Reset the injected clock back to wall time."""
    global _override_now
    _override_now = None


def advance_demo_day():
    if os.environ.get("CLUBLEDGER_ENV", "dev") not in ("dev", "test"):
        raise RuntimeError("Demo time is unavailable in production.")
    next_time = (_parse_demo(now()) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if os.environ.get("CLUBLEDGER_ENV") == "test":
        set_now(next_time)
    else:
        os.environ["CLUBLEDGER_DEMO_TIME"] = next_time
    return next_time


def _parse_demo(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def academic_year_bounds(instant: str) -> tuple[str, str, str]:
    """Compute (label, starts_at_utc, expires_at_utc) in Asia/Kolkata (+05:30).

    The academic year runs 1 Aug 00:00 IST to the next 1 Aug 00:00 IST.
    All return values are UTC ISO-8601 strings ending in 'Z'.
    """
    if instant.endswith("Z"):
        dt_utc = datetime.fromisoformat(instant[:-1]).replace(tzinfo=timezone.utc)
    else:
        dt_utc = datetime.fromisoformat(instant)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        else:
            dt_utc = dt_utc.astimezone(timezone.utc)

    dt_ist = dt_utc.astimezone(_IST)
    if dt_ist.month >= 8:
        start_year = dt_ist.year
        end_year = dt_ist.year + 1
    else:
        start_year = dt_ist.year - 1
        end_year = dt_ist.year

    label = f"{start_year}-{str(end_year)[-2:]}"

    start_ist = datetime(start_year, 8, 1, 0, 0, 0, tzinfo=_IST)
    end_ist = datetime(end_year, 8, 1, 0, 0, 0, tzinfo=_IST)

    start_utc = start_ist.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = end_ist.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return (label, start_utc, end_utc)
