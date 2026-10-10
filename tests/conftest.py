"""Pytest conftest and test outcome recorder plugin.

Provides:
- Pytest session hooks to record actual test outcomes and req markers into .pytest_results.json
- Temporary database fixture (db)
- Clock fixtures (clock, fixed_clock)
- Lazy fixtures for app_client, make_user, make_event, login_as (blocks cleanly if A/B implementations are missing)
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Dict, Generator, List
import pytest

RESULTS_PATH = Path(".pytest_results.json")

# In-memory test execution record
_TEST_RECORDS: List[Dict[str, Any]] = []
_FAILURES: List[Dict[str, Any]] = []


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register custom command-line options if needed."""
    pass


def pytest_sessionstart(session: pytest.Session) -> None:
    """Clear old test records at the beginning of the session."""
    global _TEST_RECORDS, _FAILURES
    _TEST_RECORDS = []
    _FAILURES = []
    if RESULTS_PATH.exists():
        try:
            RESULTS_PATH.unlink()
        except OSError:
            pass


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Generator[None, pytest.TestReport, None]:
    """Hook to capture test phase outcomes (setup, call, teardown)."""
    outcome = yield
    report = outcome.get_result()

    # We are interested in the test result:
    # If setup fails (e.g. error in fixture), report.when == "setup" and report.failed
    # If call fails/passes/skips, report.when == "call"
    # If skipped in setup (e.g. pytest.skip), report.when == "setup" and report.skipped
    if report.when == "call" or (report.when in ("setup", "teardown") and report.failed) or (report.when == "setup" and report.skipped):
        # Extract requirement markers: @pytest.mark.req("ID", "kind")
        req_markers = []
        for mark in item.iter_markers(name="req"):
            if len(mark.args) >= 2:
                req_markers.append({"id": mark.args[0], "kind": mark.args[1]})
            elif len(mark.args) == 1:
                req_markers.append({"id": mark.args[0], "kind": "pos"})

        status = report.outcome  # "passed", "failed", "skipped"

        # Check if already recorded to avoid duplicate entry for setup+call
        existing = next((r for r in _TEST_RECORDS if r["nodeid"] == item.nodeid), None)
        if existing:
            # Update existing outcome if it failed
            if status == "failed":
                existing["outcome"] = "failed"
                existing["message"] = str(report.longrepr)
        else:
            rec = {
                "nodeid": item.nodeid,
                "outcome": status,
                "markers": req_markers,
            }
            if status == "failed":
                rec["message"] = str(report.longrepr)
            _TEST_RECORDS.append(rec)

        if report.failed:
            _FAILURES.append({
                "nodeid": item.nodeid,
                "when": report.when,
                "message": str(report.longrepr),
            })


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Write genuine run outcomes to .pytest_results.json."""
    data = {
        "exitstatus": exitstatus,
        "tests": _TEST_RECORDS,
        "failures": _FAILURES,
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ============================================================================
# Core Fixtures (DB, Clock, Lazy components)
# ============================================================================

@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    """Provide a path to a temporary SQLite database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        path = Path(tf.name)
    try:
        yield path
    finally:
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass


@pytest.fixture
def db(temp_db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Temporary SQLite database connection with CONTRACT §0 pragmas.
    
    If migrations are implemented by Owner A, they will be applied.
    """
    conn = sqlite3.connect(str(temp_db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.row_factory = sqlite3.Row

    # Attempt to apply migrations if available
    try:
        import clubledger.core.db as core_db  # type: ignore
        if hasattr(core_db, "apply_migrations"):
            core_db.apply_migrations(conn)
    except (ImportError, AttributeError):
        pass

    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def clock() -> Generator[Any, None, None]:
    """Clock fixture interacting with core.clock if available."""
    try:
        import clubledger.core.clock as core_clock  # type: ignore
        core_clock.reset()
        yield core_clock
        core_clock.reset()
    except (ImportError, AttributeError):
        # Fallback clock wrapper for test environment before A implements core.clock
        class MockClock:
            def __init__(self) -> None:
                self._current = "2026-10-10T12:00:00Z"
            def now(self) -> str:
                return self._current
            def set_now(self, dt: str) -> None:
                self._current = dt
            def reset(self) -> None:
                self._current = "2026-10-10T12:00:00Z"
        yield MockClock()


@pytest.fixture
def app_client() -> Any:
    """Lazy FastAPI TestClient fixture. Blocked if main.py is missing."""
    try:
        from clubledger.main import app  # type: ignore
        from starlette.testclient import TestClient
        return TestClient(app)
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.skip(f"app_client blocked: application components not yet implemented ({exc})")


@pytest.fixture
def make_user(db: sqlite3.Connection) -> Any:
    """Lazy factory fixture to create a user."""
    try:
        from tests.factories import create_user
        return lambda **kwargs: create_user(db, **kwargs)
    except (ImportError, AttributeError) as exc:
        pytest.skip(f"make_user blocked: user service not yet implemented ({exc})")


@pytest.fixture
def make_event(db: sqlite3.Connection) -> Any:
    """Lazy factory fixture to create an event."""
    try:
        from tests.factories import create_event
        return lambda **kwargs: create_event(db, **kwargs)
    except (ImportError, AttributeError) as exc:
        pytest.skip(f"make_event blocked: event service not yet implemented ({exc})")


@pytest.fixture
def login_as(app_client: Any) -> Any:
    """Lazy fixture to authenticate app_client as a given user."""
    try:
        from tests.factories import login_user
        return lambda user: login_user(app_client, user)
    except (ImportError, AttributeError) as exc:
        pytest.skip(f"login_as blocked: auth components not yet implemented ({exc})")
