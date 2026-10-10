"""Unit tests for pricing and entitlement rules per CONTRACT.md §2."""

from pathlib import Path
import sqlite3
import pytest

from clubledger.core.db import apply_migrations, connect
from clubledger.core.pricing import active_membership, merch_price, ticket_price


@pytest.fixture
def db_conn(tmp_path: Path):
    db_file = tmp_path / "pricing_test.db"
    conn = connect(str(db_file))
    apply_migrations(conn)

    # Insert open term
    conn.execute(
        "INSERT INTO terms (id, label, starts_at, ends_at, status, created_at) "
        "VALUES (1, '2026-Fall', '2026-08-01T00:00:00Z', NULL, 'OPEN', '2026-08-01T00:00:00Z');"
    )

    # Insert active and inactive users
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (1, 'alice@example.com', 'Alice', 'scrypt$123', 1, '2026-08-01T00:00:00Z');"
    )
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (2, 'bob@example.com', 'Bob', 'scrypt$123', 0, '2026-08-01T00:00:00Z');"
    )

    # Create membership schema tables manually for testing pricing rules in isolation
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS membership_plans (
            id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
            dues_paise INTEGER NOT NULL, ticket_discount_bps INTEGER NOT NULL,
            merch_discount_bps INTEGER NOT NULL, is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        ) STRICT;
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memberships (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            plan_id INTEGER NOT NULL REFERENCES membership_plans(id),
            membership_year TEXT NOT NULL, status TEXT NOT NULL,
            starts_at TEXT NOT NULL, expires_at TEXT NOT NULL,
            member_code TEXT, qr_token TEXT, payment_id INTEGER,
            verified_by INTEGER, verified_at TEXT, created_at TEXT NOT NULL
        ) STRICT;
        """
    )

    # Create events table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL REFERENCES terms(id),
            title TEXT NOT NULL, venue TEXT NOT NULL, starts_at TEXT NOT NULL, ends_at TEXT NOT NULL,
            capacity INTEGER NOT NULL, member_price_paise INTEGER NOT NULL,
            public_price_paise INTEGER NOT NULL, max_per_order INTEGER NOT NULL DEFAULT 4,
            status TEXT NOT NULL, created_at TEXT NOT NULL
        ) STRICT;
        """
    )

    # Seed plan 1 (15% ticket discount, 10% merch discount)
    conn.execute(
        "INSERT INTO membership_plans (id, code, name, dues_paise, ticket_discount_bps, merch_discount_bps, created_at) "
        "VALUES (1, 'standard', 'Standard Plan', 25000, 1500, 1000, '2026-08-01T00:00:00Z');"
    )
    # Seed plan 2 (40% ticket discount - improves event member price)
    conn.execute(
        "INSERT INTO membership_plans (id, code, name, dues_paise, ticket_discount_bps, merch_discount_bps, created_at) "
        "VALUES (2, 'vip', 'VIP Plan', 50000, 4000, 2500, '2026-08-01T00:00:00Z');"
    )

    conn.commit()
    yield conn
    conn.close()


def test_active_membership_resolution(db_conn: sqlite3.Connection):
    # Active membership covering 2026-08-01 to 2027-08-01
    db_conn.execute(
        """
        INSERT INTO memberships (
            id, user_id, plan_id, membership_year, status,
            starts_at, expires_at, member_code, qr_token, created_at
        ) VALUES (
            1, 1, 1, '2026-27', 'ACTIVE',
            '2026-08-01T00:00:00Z', '2027-08-01T00:00:00Z', 'MEM-001', 'qr-001', '2026-08-01T00:00:00Z'
        );
        """
    )
    db_conn.commit()

    # Instant inside boundary
    mem = active_membership(db_conn, user_id=1, at="2026-09-01T12:00:00Z")
    assert mem is not None
    assert mem.id == 1
    assert mem.user_id == 1
    assert mem.status == "ACTIVE"

    # Instant before starts_at
    mem_before = active_membership(db_conn, user_id=1, at="2026-07-31T23:59:59Z")
    assert mem_before is None

    # Instant at or after expires_at
    mem_after = active_membership(db_conn, user_id=1, at="2027-08-01T00:00:00Z")
    assert mem_after is None

    # Deactivated user account
    db_conn.execute(
        """
        INSERT INTO memberships (
            id, user_id, plan_id, membership_year, status,
            starts_at, expires_at, member_code, qr_token, created_at
        ) VALUES (
            2, 2, 1, '2026-27', 'ACTIVE',
            '2026-08-01T00:00:00Z', '2027-08-01T00:00:00Z', 'MEM-002', 'qr-002', '2026-08-01T00:00:00Z'
        );
        """
    )
    db_conn.commit()
    mem_deactivated = active_membership(db_conn, user_id=2, at="2026-09-01T12:00:00Z")
    assert mem_deactivated is None


def test_ticket_price_member_and_public(db_conn: sqlite3.Connection):
    # Event: public price 1000 INR (100,000 paise), member price 750 INR (75,000 paise)
    db_conn.execute(
        """
        INSERT INTO events (
            id, term_id, title, venue, starts_at, ends_at, capacity,
            member_price_paise, public_price_paise, status, created_at
        ) VALUES (
            1, 1, 'Hackathon', 'Hall A', '2026-09-10T10:00:00Z', '2026-09-10T20:00:00Z', 100,
            75000, 100000, 'ON_SALE', '2026-08-01T00:00:00Z'
        );
        """
    )
    db_conn.commit()

    # User 1 without active membership pays public price
    price, tier = ticket_price(
        db_conn, event_id=1, user_id=1, at="2026-09-01T00:00:00Z"
    )
    assert price == 100000
    assert tier == "PUBLIC"

    # Grant standard plan (15% discount -> 85,000 paise; event member price is 75,000 paise -> min is 75,000)
    db_conn.execute(
        """
        INSERT INTO memberships (
            id, user_id, plan_id, membership_year, status,
            starts_at, expires_at, member_code, qr_token, created_at
        ) VALUES (
            1, 1, 1, '2026-27', 'ACTIVE',
            '2026-08-01T00:00:00Z', '2027-08-01T00:00:00Z', 'MEM-001', 'qr-001', '2026-08-01T00:00:00Z'
        );
        """
    )
    db_conn.commit()

    price, tier = ticket_price(
        db_conn, event_id=1, user_id=1, at="2026-09-01T00:00:00Z"
    )
    assert price == 75000
    assert tier == "MEMBER"

    # Update to VIP plan (40% discount -> 60,000 paise; min(75000, 60000) is 60,000)
    db_conn.execute("UPDATE memberships SET plan_id = 2 WHERE id = 1;")
    db_conn.commit()

    price_vip, tier_vip = ticket_price(
        db_conn, event_id=1, user_id=1, at="2026-09-01T00:00:00Z"
    )
    assert price_vip == 60000
    assert tier_vip == "MEMBER"


def test_merch_price_member_and_public(db_conn: sqlite3.Connection):
    base_price = 50000  # 500 INR

    # Anonymous / non-member
    price, tier = merch_price(
        db_conn, base_paise=base_price, user_id=999, at="2026-09-01T00:00:00Z"
    )
    assert price == 50000
    assert tier == "PUBLIC"

    # Member with Plan 1 (10% discount -> 45,000 paise)
    db_conn.execute(
        """
        INSERT INTO memberships (
            id, user_id, plan_id, membership_year, status,
            starts_at, expires_at, member_code, qr_token, created_at
        ) VALUES (
            1, 1, 1, '2026-27', 'ACTIVE',
            '2026-08-01T00:00:00Z', '2027-08-01T00:00:00Z', 'MEM-001', 'qr-001', '2026-08-01T00:00:00Z'
        );
        """
    )
    db_conn.commit()

    price_mem, tier_mem = merch_price(
        db_conn, base_paise=base_price, user_id=1, at="2026-09-01T00:00:00Z"
    )
    assert price_mem == 45000
    assert tier_mem == "MEMBER"
