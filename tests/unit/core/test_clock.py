"""Tests for deterministic clock controls and academic year boundaries per CONTRACT G4, G9."""

from datetime import datetime, timezone
import os
import re
import pytest

from clubledger.core import clock


@pytest.fixture(autouse=True)
def clean_clock():
    original_env = os.environ.get("CLUBLEDGER_ENV")
    clock.reset()
    yield
    clock.reset()
    if original_env is not None:
        os.environ["CLUBLEDGER_ENV"] = original_env
    else:
        os.environ.pop("CLUBLEDGER_ENV", None)


def test_now_returns_utc_iso_format() -> None:
    current = clock.now()
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", current)


def test_set_now_works_under_test_env() -> None:
    os.environ["CLUBLEDGER_ENV"] = "test"
    target = "2026-08-15T10:30:00Z"
    clock.set_now(target)
    assert clock.now() == target

    # Also test passing datetime object
    dt = datetime(2026, 9, 1, 14, 0, 0, tzinfo=timezone.utc)
    clock.set_now(dt)
    assert clock.now() == "2026-09-01T14:00:00Z"

    clock.reset()
    assert clock.now() != "2026-09-01T14:00:00Z"


def test_set_now_raises_outside_test_env() -> None:
    for env in ("dev", "prod"):
        os.environ["CLUBLEDGER_ENV"] = env
        with pytest.raises(
            RuntimeError, match="allowed only when CLUBLEDGER_ENV == 'test'"
        ):
            clock.set_now("2026-08-15T10:30:00Z")


def test_academic_year_bounds() -> None:
    # 1. During academic year
    label, start_utc, exp_utc = clock.academic_year_bounds("2026-10-10T12:00:00Z")
    assert label == "2026-27"
    assert start_utc == "2026-07-31T18:30:00Z"
    assert exp_utc == "2027-07-31T18:30:00Z"

    # 2. Exact boundary: 1 Aug 00:00:00 IST = 31 Jul 18:30:00Z
    label_b, start_b, exp_b = clock.academic_year_bounds("2026-07-31T18:30:00Z")
    assert label_b == "2026-27"
    assert start_b == "2026-07-31T18:30:00Z"
    assert exp_b == "2027-07-31T18:30:00Z"

    # 3. 1 second before boundary: 31 Jul 23:59:59 IST = 31 Jul 18:29:59Z
    label_prev, start_prev, exp_prev = clock.academic_year_bounds(
        "2026-07-31T18:29:59Z"
    )
    assert label_prev == "2025-26"
    assert start_prev == "2025-07-31T18:30:00Z"
    assert exp_prev == "2026-07-31T18:30:00Z"

    # 4. Invariant: previous year's expires_at equals current year's starts_at exactly
    assert exp_prev == start_b
