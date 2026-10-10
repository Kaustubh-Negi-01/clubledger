"""Tests for migration runner: prefix rules, gap rejection, checksum mismatch, and schema constraints."""

from pathlib import Path
import sqlite3
import pytest

from clubledger.core.db import apply_migrations, connect
from clubledger.core.errors import (
    MigrationChecksumError,
    MigrationDuplicateError,
    MigrationError,
    MigrationGapError,
)


def test_apply_migrations_genuine_sequence(tmp_path: Path) -> None:
    db_file = tmp_path / "test_mig.db"
    conn = connect(str(db_file))
    try:
        applied = apply_migrations(conn)
        assert len(applied) >= 2
        assert applied == list(range(1, len(applied) + 1))
        assert 1 in applied and 2 in applied

        # Verify tables created
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        }
        assert "users" in tables
        assert "roles" in tables
        assert "permissions" in tables
        assert "terms" in tables
        assert "sessions" in tables
        assert "audit_log" in tables
        assert "idempotency_keys" in tables
        assert "schema_migrations" in tables
        assert "payments" in tables
        assert "payment_events" in tables

        # Verify schema_migrations records
        rows = conn.execute(
            "SELECT number, filename, checksum FROM schema_migrations ORDER BY number ASC;"
        ).fetchall()
        assert len(rows) == len(applied)
        assert rows[0]["number"] == 1
        assert rows[0]["filename"] == "0001_core.sql"
        assert rows[1]["number"] == 2
        assert rows[1]["filename"] == "0002_payments.sql"

        # Rerun is a no-op
        rerun_applied = apply_migrations(conn)
        assert rerun_applied == []
    finally:
        conn.close()


def test_prefix_runner_controlled_migrations_dir(tmp_path: Path) -> None:
    mig_dir = tmp_path / "migrations_prefix"
    mig_dir.mkdir()
    (mig_dir / "0001_core.sql").write_text(
        "CREATE TABLE t1 (id INTEGER PRIMARY KEY) STRICT;\n"
        "CREATE TABLE schema_migrations (number INTEGER PRIMARY KEY, filename TEXT NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL) STRICT;\n",
        encoding="utf-8",
    )
    (mig_dir / "0002_two.sql").write_text(
        "CREATE TABLE t2 (id INTEGER PRIMARY KEY) STRICT;\n", encoding="utf-8"
    )

    db_file = tmp_path / "prefix.db"
    conn = connect(str(db_file))
    try:
        applied = apply_migrations(conn, migrations_dir=mig_dir)
        assert applied == [1, 2]
    finally:
        conn.close()


def test_migrations_with_simulated_0001_to_0006_tree(tmp_path: Path) -> None:
    mig_dir = tmp_path / "migrations_full"
    mig_dir.mkdir()
    (mig_dir / "0001_core.sql").write_text(
        "CREATE TABLE t1 (id INTEGER PRIMARY KEY) STRICT;\n"
        "CREATE TABLE schema_migrations (number INTEGER PRIMARY KEY, filename TEXT NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL) STRICT;\n",
        encoding="utf-8",
    )
    for i in range(2, 7):
        (mig_dir / f"000{i}_step{i}.sql").write_text(
            f"CREATE TABLE t{i} (id INTEGER PRIMARY KEY) STRICT;\n",
            encoding="utf-8",
        )

    db_file = tmp_path / "full.db"
    conn = connect(str(db_file))
    try:
        applied = apply_migrations(conn, migrations_dir=mig_dir)
        assert applied == [1, 2, 3, 4, 5, 6]
        rerun = apply_migrations(conn, migrations_dir=mig_dir)
        assert rerun == []
    finally:
        conn.close()


def test_rejects_internal_gap(tmp_path: Path) -> None:
    # Setup custom migrations directory with an internal gap: 0001, 0002, 0004 (missing 0003)
    mig_dir = tmp_path / "migrations_gap"
    mig_dir.mkdir()
    (mig_dir / "0001_core.sql").write_text(
        "CREATE TABLE t1 (id INTEGER PRIMARY KEY) STRICT;\n"
        "CREATE TABLE schema_migrations (number INTEGER PRIMARY KEY, filename TEXT NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL) STRICT;\n",
        encoding="utf-8",
    )
    (mig_dir / "0002_two.sql").write_text(
        "CREATE TABLE t2 (id INTEGER PRIMARY KEY) STRICT;\n", encoding="utf-8"
    )
    (mig_dir / "0004_four.sql").write_text(
        "CREATE TABLE t4 (id INTEGER PRIMARY KEY) STRICT;\n", encoding="utf-8"
    )

    db_file = tmp_path / "gap.db"
    conn = connect(str(db_file))
    try:
        with pytest.raises(MigrationGapError, match="missing 0003"):
            apply_migrations(conn, migrations_dir=mig_dir)

        # Nothing should be applied
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='t1';"
            ).fetchall()
        ]
        assert len(tables) == 0
    finally:
        conn.close()


def test_rejects_changed_applied_migration_checksum(tmp_path: Path) -> None:
    mig_dir = tmp_path / "migrations_checksum"
    mig_dir.mkdir()
    f1 = mig_dir / "0001_core.sql"
    f1.write_text(
        "CREATE TABLE t1 (id INTEGER PRIMARY KEY) STRICT;\n"
        "CREATE TABLE schema_migrations (number INTEGER PRIMARY KEY, filename TEXT NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL) STRICT;\n",
        encoding="utf-8",
    )

    db_file = tmp_path / "checksum.db"
    conn = connect(str(db_file))
    try:
        # First apply migration 1
        applied = apply_migrations(conn, migrations_dir=mig_dir)
        assert applied == [1]

        # Now tamper with 0001_core.sql
        f1.write_text(
            "CREATE TABLE t1 (id INTEGER PRIMARY KEY, extra TEXT) STRICT;\n",
            encoding="utf-8",
        )

        # Next run must fail with MigrationChecksumError naming the file
        with pytest.raises(
            MigrationChecksumError,
            match="Checksum mismatch for migration 0001_core.sql",
        ):
            apply_migrations(conn, migrations_dir=mig_dir)
    finally:
        conn.close()


def test_rejects_duplicate_migration_numbers(tmp_path: Path) -> None:
    mig_dir = tmp_path / "migrations_dup"
    mig_dir.mkdir()
    (mig_dir / "0001_first.sql").write_text(
        "CREATE TABLE a (id INTEGER PRIMARY KEY);", encoding="utf-8"
    )
    (mig_dir / "0001_second.sql").write_text(
        "CREATE TABLE b (id INTEGER PRIMARY KEY);", encoding="utf-8"
    )

    db_file = tmp_path / "dup.db"
    conn = connect(str(db_file))
    try:
        with pytest.raises(
            MigrationDuplicateError, match="Duplicate migration number 0001"
        ):
            apply_migrations(conn, migrations_dir=mig_dir)
    finally:
        conn.close()


def test_rejects_missing_previously_applied_file(tmp_path: Path) -> None:
    mig_dir = tmp_path / "migrations_missing_applied"
    mig_dir.mkdir()
    f1 = mig_dir / "0001_core.sql"
    f1.write_text(
        "CREATE TABLE t1 (id INTEGER PRIMARY KEY) STRICT;\n"
        "CREATE TABLE schema_migrations (number INTEGER PRIMARY KEY, filename TEXT NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL) STRICT;\n",
        encoding="utf-8",
    )
    (mig_dir / "0002_two.sql").write_text(
        "CREATE TABLE t2 (id INTEGER PRIMARY KEY) STRICT;\n", encoding="utf-8"
    )

    db_file = tmp_path / "missing_applied.db"
    conn = connect(str(db_file))
    try:
        applied = apply_migrations(conn, migrations_dir=mig_dir)
        assert applied == [1, 2]

        # Delete applied migration 0001_core.sql
        f1.unlink()

        # Normal CLI run must fail naming the missing applied file
        with pytest.raises(
            MigrationError,
            match="Previously applied migration file missing: 0001_core.sql",
        ):
            apply_migrations(conn, migrations_dir=mig_dir)
    finally:
        conn.close()


def test_rejects_renamed_previously_applied_file(tmp_path: Path) -> None:
    mig_dir = tmp_path / "migrations_renamed_applied"
    mig_dir.mkdir()
    f1 = mig_dir / "0001_core.sql"
    f1.write_text(
        "CREATE TABLE t1 (id INTEGER PRIMARY KEY) STRICT;\n"
        "CREATE TABLE schema_migrations (number INTEGER PRIMARY KEY, filename TEXT NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL) STRICT;\n",
        encoding="utf-8",
    )

    db_file = tmp_path / "renamed_applied.db"
    conn = connect(str(db_file))
    try:
        applied = apply_migrations(conn, migrations_dir=mig_dir)
        assert applied == [1]

        # Rename 0001_core.sql to 0001_renamed.sql
        f1.rename(mig_dir / "0001_renamed.sql")

        # Normal CLI run must fail naming the renamed file
        with pytest.raises(
            MigrationError,
            match="Previously applied migration file renamed: expected 0001_core.sql",
        ):
            apply_migrations(conn, migrations_dir=mig_dir)
    finally:
        conn.close()


def test_subset_fixture_mode(tmp_path: Path) -> None:
    # Test-only subset fixture can apply an explicit list of files
    db_file = tmp_path / "subset.db"
    conn = connect(str(db_file))
    try:
        applied = apply_migrations(conn, files=["0001_core.sql"])
        assert applied == [1]

        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        }
        assert "users" in tables
        assert "payments" not in tables
    finally:
        conn.close()


def test_tables_are_strict(tmp_path: Path) -> None:
    db_file = tmp_path / "strict.db"
    conn = connect(str(db_file))
    try:
        apply_migrations(conn)

        # In SQLite STRICT tables, wrong types (e.g. string for integer column) raise an error
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
                "VALUES ('not-an-int', 'test@example.com', 'Name', 'hash', 1, '2026-08-01T00:00:00Z');"
            )
    finally:
        conn.close()


def test_payment_events_outcome_immutable_trigger(tmp_path: Path) -> None:
    db_file = tmp_path / "trigger.db"
    conn = connect(str(db_file))
    try:
        apply_migrations(conn)

        # Insert a payment event
        conn.execute(
            "INSERT INTO payment_events (id, event_id, body_sha256, raw_body, type, claimed_public_id, "
            "amount_paise, currency, outcome, created_at) "
            "VALUES (1, 'evt_1', 'hash', '{}', 'payment.succeeded', 'pub_1', 1000, 'INR', 'APPLIED', '2026-08-01T00:00:00Z');"
        )

        # Attempt to mutate outcome directly should abort via trigger
        with pytest.raises(
            sqlite3.IntegrityError, match="payment_events.outcome is immutable"
        ):
            conn.execute(
                "UPDATE payment_events SET outcome = 'NO_EFFECT' WHERE id = 1;"
            )
    finally:
        conn.close()


def test_cli_migrate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from clubledger.cli import main

    db_file = tmp_path / "cli_test.db"
    exit_code = main(["migrate", "--db", str(db_file)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Applied migrations: [" in captured.out
    assert "1" in captured.out and "2" in captured.out

    # Second run is idempotent
    exit_code_second = main(["migrate", "--db", str(db_file)])
    assert exit_code_second == 0
    captured_second = capsys.readouterr()
    assert "No pending migrations" in captured_second.out

    # Test seed command
    exit_code_seed = main(["seed", "--db", str(db_file)])
    assert exit_code_seed == 0
    captured_seed = capsys.readouterr()
    assert "Seeded roles and permissions successfully." in captured_seed.out

    # Second seed is idempotent
    exit_code_seed_again = main(["seed", "--db", str(db_file)])
    assert exit_code_seed_again == 0
