"""Tests for database connection pragmas, unit_of_work, commit, and rollback."""

import sqlite3
import tempfile
from pathlib import Path
import pytest

from clubledger.core.db import connect, unit_of_work


def test_connect_sets_required_pragmas(tmp_path: Path) -> None:
    db_file = tmp_path / "test.db"
    conn = connect(str(db_file))
    try:
        fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert fk == 1

        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0].upper()
        assert journal_mode == "WAL"

        busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert busy_timeout == 5000

        synchronous = conn.execute("PRAGMA synchronous;").fetchone()[0]
        # NORMAL is synchronous == 1 in SQLite
        assert synchronous == 1
    finally:
        conn.close()


def test_unit_of_work_commits_on_success(tmp_path: Path) -> None:
    db_file = tmp_path / "test_commit.db"
    conn_setup = connect(str(db_file))
    conn_setup.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, val TEXT);")
    conn_setup.close()

    with unit_of_work(str(db_file)) as conn:
        conn.execute("INSERT INTO sample (id, val) VALUES (1, 'hello');")

    # Verify committed in a new connection
    conn_check = connect(str(db_file))
    try:
        row = conn_check.execute("SELECT val FROM sample WHERE id = 1;").fetchone()
        assert row is not None
        assert row["val"] == "hello"
    finally:
        conn_check.close()


def test_unit_of_work_rolls_back_on_exception(tmp_path: Path) -> None:
    db_file = tmp_path / "test_rollback.db"
    conn_setup = connect(str(db_file))
    conn_setup.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, val TEXT);")
    conn_setup.close()

    with pytest.raises(RuntimeError, match="Simulated error"):
        with unit_of_work(str(db_file)) as conn:
            conn.execute("INSERT INTO sample (id, val) VALUES (1, 'should_rollback');")
            raise RuntimeError("Simulated error")

    # Verify rolled back in a new connection
    conn_check = connect(str(db_file))
    try:
        row = conn_check.execute("SELECT val FROM sample WHERE id = 1;").fetchone()
        assert row is None
    finally:
        conn_check.close()


def test_unit_of_work_prevents_nested_transactions(tmp_path: Path) -> None:
    db_file = tmp_path / "test_nested.db"
    with unit_of_work(str(db_file)) as conn:
        assert conn.in_transaction is True
        # Attempting nested BEGIN inside unit_of_work must fail
        with pytest.raises(sqlite3.OperationalError, match="cannot start a transaction within a transaction"):
            conn.execute("BEGIN IMMEDIATE")
