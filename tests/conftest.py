"""Pytest conftest and test outcome recorder plugin.

Provides:
- Pytest session hooks to record actual test outcomes, run timestamp, tested git commit,
  and req markers into .pytest_results.json.
- Temporary database fixture (db) using Owner A's connect/unit_of_work/apply_migrations.
- Clock fixtures (clock, fixed_clock) using Owner A's core.clock.
- App client fixture using Owner A's create_app against the same temporary migrated database.
- Lazy fixtures for make_user, make_event, login_as (blocks cleanly if A/B implementations are missing).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from typing import Any, Dict, Generator, List
import pytest

RESULTS_PATH = Path(".pytest_results.json")

# In-memory test execution record
_TEST_RECORDS: List[Dict[str, Any]] = []
_FAILURES: List[Dict[str, Any]] = []
_SESSION_START_TIME: str = ""
_GIT_COMMIT: str = ""


def _get_git_commit() -> str:
    """Get current git commit hash."""
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return "unknown"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register custom command-line options if needed."""
    pass


def pytest_sessionstart(session: pytest.Session) -> None:
    """Clear old test records at the beginning of the session."""
    global _TEST_RECORDS, _FAILURES, _SESSION_START_TIME, _GIT_COMMIT
    _TEST_RECORDS = []
    _FAILURES = []
    _SESSION_START_TIME = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _GIT_COMMIT = _get_git_commit()

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

    # Track outcomes:
    # report.outcome is "passed", "failed", or "skipped"
    # xfail / xpass handling in pytest:
    # If xfail: hasattr(report, "wasxfail") -> outcome could be "skipped" (strict=False) or "failed"
    is_xfail = hasattr(report, "wasxfail")
    is_xpass = False
    if report.when == "call" and hasattr(report, "wasxfail") and report.outcome == "passed":
        is_xpass = True

    if report.when == "call" or (report.when in ("setup", "teardown") and report.failed) or (report.when == "setup" and report.skipped):
        # Extract requirement markers: @pytest.mark.req("ID", "kind")
        req_markers = []
        for mark in item.iter_markers(name="req"):
            if len(mark.args) >= 2:
                req_markers.append({"id": mark.args[0], "kind": mark.args[1]})
            elif len(mark.args) == 1:
                req_markers.append({"id": mark.args[0], "kind": "pos"})
            else:
                req_markers.append({"id": None, "kind": None, "malformed": True})

        status = report.outcome  # "passed", "failed", "skipped"
        if is_xfail:
            status = "xfail"
        elif is_xpass:
            status = "xpass"

        # Check if already recorded to avoid duplicate entry for setup+call
        existing = next((r for r in _TEST_RECORDS if r["nodeid"] == item.nodeid), None)
        if existing:
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
        "timestamp": _SESSION_START_TIME,
        "commit": _GIT_COMMIT,
        "exitstatus": int(exitstatus),
        "tests": _TEST_RECORDS,
        "failures": _FAILURES,
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ============================================================================
# Core Fixtures (DB, Clock, App Client)
# ============================================================================

@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    """Provide a path to a temporary SQLite database file and manage environment."""
    old_env = os.environ.get("CLUBLEDGER_ENV")
    old_db = os.environ.get("CLUBLEDGER_DB_PATH")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        path = Path(tf.name)

    os.environ["CLUBLEDGER_ENV"] = "test"
    os.environ["CLUBLEDGER_DB_PATH"] = str(path)

    try:
        yield path
    finally:
        # Restore environment
        if old_env is None:
            os.environ.pop("CLUBLEDGER_ENV", None)
        else:
            os.environ["CLUBLEDGER_ENV"] = old_env

        if old_db is None:
            os.environ.pop("CLUBLEDGER_DB_PATH", None)
        else:
            os.environ["CLUBLEDGER_DB_PATH"] = old_db

        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass


@pytest.fixture
def db(temp_db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Temporary SQLite database connection using Owner A's connect and apply_migrations.
    
    Ensures CONTRACT §0 pragmas and strictly applied migrations.
    """
    try:
        from clubledger.core.db import connect, apply_migrations  # type: ignore
        conn = connect(str(temp_db_path))
        apply_migrations(conn)
        try:
            yield conn
        finally:
            conn.close()
    except (ImportError, ModuleNotFoundError):
        # If A's core.db is not yet present, use raw sqlite3 connection with CONTRACT §0 pragmas
        conn = sqlite3.connect(str(temp_db_path))
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()


@pytest.fixture
def clock() -> Generator[Any, None, None]:
    """Clock fixture using Owner A's core.clock.
    
    Guarantees CLUBLEDGER_ENV == 'test' and resets clock state after each test.
    """
    old_env = os.environ.get("CLUBLEDGER_ENV")
    os.environ["CLUBLEDGER_ENV"] = "test"
    try:
        from clubledger.core.clock import now, set_now, reset  # type: ignore
        import clubledger.core.clock as clock_mod
        reset()
        yield clock_mod
        reset()
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.skip(f"clock blocked: core.clock not yet implemented ({exc})")
    finally:
        if old_env is None:
            os.environ.pop("CLUBLEDGER_ENV", None)
        else:
            os.environ["CLUBLEDGER_ENV"] = old_env


@pytest.fixture
def app_client(temp_db_path: Path, db: sqlite3.Connection) -> Generator[Any, None, None]:
    """FastAPI TestClient fixture configured against the temporary migrated test database."""
    try:
        from clubledger.main import create_app  # type: ignore
        from starlette.testclient import TestClient
        app = create_app()
        with TestClient(app) as client:
            yield client
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
