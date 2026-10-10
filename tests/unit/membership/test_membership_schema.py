import sqlite3
import pytest

from clubledger.core.db import apply_migrations, connect


def get_migrated_db() -> sqlite3.Connection:
    conn = connect(":memory:")
    # Controlled-prefix genuine-file subset 0001..0005 per TURBO_B.txt
    applied = apply_migrations(
        conn,
        files=[
            "0001_core.sql",
            "0002_payments.sql",
            "0003_membership.sql",
            "0004_events.sql",
            "0005_store.sql",
        ],
    )
    assert applied == [1, 2, 3, 4, 5], f"Expected migrations 1..5, got {applied}"
    # Verify idempotent rerun on controlled prefix
    rerun = apply_migrations(
        conn,
        files=[
            "0001_core.sql",
            "0002_payments.sql",
            "0003_membership.sql",
            "0004_events.sql",
            "0005_store.sql",
        ],
    )
    assert rerun == [], f"Expected empty rerun, got {rerun}"
    return conn


def test_membership_clean_migration_and_idempotent_rerun():
    conn = connect(":memory:")
    # Integration test validates the actual contiguous discovered migration sequence including 0006+
    applied = apply_migrations(conn)
    assert len(applied) >= 5
    assert applied[:5] == [1, 2, 3, 4, 5]
    rerun = apply_migrations(conn)
    assert rerun == [], f"Expected empty rerun, got {rerun}"

    rows = conn.execute(
        "SELECT number, filename FROM schema_migrations ORDER BY number ASC;"
    ).fetchall()
    numbers = [r["number"] for r in rows]
    assert numbers[:5] == [1, 2, 3, 4, 5]
    row_mem = [r for r in rows if r["number"] == 3][0]
    assert row_mem["filename"] == "0003_membership.sql"
    conn.close()


def test_membership_plan_and_creation():
    conn = get_migrated_db()
    try:
        conn.execute(
            "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (1, "alice@test.com", "Alice", "scrypt_hash", 1, "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO terms (id, label, starts_at, ends_at, status, closed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?);",
            (1, "Fall 2026", "2026-08-01T00:00:00Z", None, "OPEN", None, "2026-08-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO payments (id, public_id, user_id, purpose, ref_table, ref_id, amount_paise, currency, status, fulfillment, term_id, succeeded_at, settled_at, refunded_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (1, "pay_1", 1, "DUES", "memberships", 1, 1500, "INR", "SUCCEEDED", "FULFILLED", 1, "2026-10-10T00:00:00Z", None, None, "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO membership_plans (id, code, name, dues_paise, ticket_discount_bps, merch_discount_bps, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
            (1, "STANDARD", "Standard Plan", 1500, 2000, 1000, 1, "2026-10-10T00:00:00Z"),
        )

        # Valid PENDING membership without member_code/qr_token
        conn.execute(
            "INSERT INTO memberships (id, user_id, plan_id, membership_year, status, starts_at, expires_at, member_code, qr_token, payment_id, verified_by, verified_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (1, 1, 1, "2026-27", "PENDING", "2026-08-01T00:00:00Z", "2027-08-01T00:00:00Z", None, None, None, None, None, "2026-10-10T00:00:00Z"),
        )

        row = conn.execute(
            "SELECT status, membership_year FROM memberships WHERE id = 1;"
        ).fetchone()
        assert row["status"] == "PENDING"
        assert row["membership_year"] == "2026-27"
    finally:
        conn.close()


def test_membership_active_requires_code_and_token():
    conn = get_migrated_db()
    try:
        conn.execute(
            "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (1, "alice@test.com", "Alice", "scrypt_hash", 1, "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO membership_plans (id, code, name, dues_paise, ticket_discount_bps, merch_discount_bps, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
            (1, "STANDARD", "Standard Plan", 1500, 2000, 1000, 1, "2026-10-10T00:00:00Z"),
        )

        # ACTIVE with NULL member_code / qr_token must fail CHECK constraint
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO memberships (id, user_id, plan_id, membership_year, status, starts_at, expires_at, member_code, qr_token, payment_id, verified_by, verified_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                (1, 1, 1, "2026-27", "ACTIVE", "2026-08-01T00:00:00Z", "2027-08-01T00:00:00Z", None, None, None, None, None, "2026-10-10T00:00:00Z"),
            )
    finally:
        conn.close()


def test_membership_expiry_must_exceed_starts_at():
    conn = get_migrated_db()
    try:
        conn.execute(
            "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (1, "alice@test.com", "Alice", "scrypt_hash", 1, "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO membership_plans (id, code, name, dues_paise, ticket_discount_bps, merch_discount_bps, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
            (1, "STANDARD", "Standard Plan", 1500, 2000, 1000, 1, "2026-10-10T00:00:00Z"),
        )

        # expires_at <= starts_at must fail CHECK (expires_at > starts_at)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO memberships (id, user_id, plan_id, membership_year, status, starts_at, expires_at, member_code, qr_token, payment_id, verified_by, verified_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                (1, 1, 1, "2026-27", "PENDING", "2027-08-01T00:00:00Z", "2026-08-01T00:00:00Z", None, None, None, None, None, "2026-10-10T00:00:00Z"),
            )
    finally:
        conn.close()


def test_membership_unique_live_per_academic_year():
    conn = get_migrated_db()
    try:
        conn.execute(
            "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (1, "alice@test.com", "Alice", "scrypt_hash", 1, "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO membership_plans (id, code, name, dues_paise, ticket_discount_bps, merch_discount_bps, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
            (1, "STANDARD", "Standard Plan", 1500, 2000, 1000, 1, "2026-10-10T00:00:00Z"),
        )

        conn.execute(
            "INSERT INTO memberships (id, user_id, plan_id, membership_year, status, starts_at, expires_at, member_code, qr_token, payment_id, verified_by, verified_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (1, 1, 1, "2026-27", "ACTIVE", "2026-08-01T00:00:00Z", "2027-08-01T00:00:00Z", "M001", "QR001", None, None, None, "2026-10-10T00:00:00Z"),
        )

        # Second live (PENDING or ACTIVE) membership in same year for same user must violate UNIQUE index
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO memberships (id, user_id, plan_id, membership_year, status, starts_at, expires_at, member_code, qr_token, payment_id, verified_by, verified_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                (2, 1, 1, "2026-27", "PENDING", "2026-08-01T00:00:00Z", "2027-08-01T00:00:00Z", None, None, None, None, None, "2026-10-10T00:00:00Z"),
            )
    finally:
        conn.close()
