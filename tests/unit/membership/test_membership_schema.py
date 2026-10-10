import sqlite3
from pathlib import Path
import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


def get_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    # Minimal prerequisite mock schema for foreign keys (core users & terms, payments)
    conn.executescript("""
    CREATE TABLE users (
      id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
      name TEXT NOT NULL, password_hash TEXT NOT NULL,
      is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
      created_at TEXT NOT NULL
    ) STRICT;
    CREATE TABLE terms (
      id INTEGER PRIMARY KEY, label TEXT NOT NULL UNIQUE, starts_at TEXT NOT NULL,
      ends_at TEXT, status TEXT NOT NULL CHECK (status IN ('OPEN','CLOSED')),
      closed_at TEXT, created_at TEXT NOT NULL
    ) STRICT;
    CREATE TABLE payments (
      id INTEGER PRIMARY KEY, public_id TEXT NOT NULL UNIQUE,
      user_id INTEGER NOT NULL REFERENCES users(id),
      purpose TEXT NOT NULL, ref_table TEXT NOT NULL, ref_id INTEGER NOT NULL,
      amount_paise INTEGER NOT NULL, currency TEXT NOT NULL,
      status TEXT NOT NULL, fulfillment TEXT NOT NULL,
      term_id INTEGER NOT NULL REFERENCES terms(id), created_at TEXT NOT NULL
    ) STRICT;
    """)
    # Apply 0003_membership.sql
    sql = (MIGRATIONS_DIR / "0003_membership.sql").read_text(encoding="utf-8")
    conn.executescript(sql)
    return conn


def test_membership_plan_and_creation():
    conn = get_db()
    conn.execute("INSERT INTO users VALUES (1, 'alice@test.com', 'Alice', 'hash', 1, '2026-10-10T00:00:00Z')")
    conn.execute("INSERT INTO terms VALUES (1, 'Fall 2026', '2026-08-01T00:00:00Z', NULL, 'OPEN', NULL, '2026-08-01T00:00:00Z')")
    conn.execute("INSERT INTO payments VALUES (1, 'pay_1', 1, 'DUES', 'memberships', 1, 1500, 'INR', 'SUCCEEDED', 'FULFILLED', 1, '2026-10-10T00:00:00Z')")
    conn.execute("INSERT INTO membership_plans VALUES (1, 'STANDARD', 'Standard Plan', 1500, 2000, 1000, 1, '2026-10-10T00:00:00Z')")
    
    # Valid PENDING membership without member_code/qr_token
    conn.execute("INSERT INTO memberships VALUES (1, 1, 1, '2026-27', 'PENDING', '2026-08-01T00:00:00Z', '2027-08-01T00:00:00Z', NULL, NULL, NULL, NULL, NULL, '2026-10-10T00:00:00Z')")
    
    cur = conn.execute("SELECT status, membership_year FROM memberships WHERE id = 1")
    row = cur.fetchone()
    assert row == ('PENDING', '2026-27')


def test_membership_active_requires_code_and_token():
    conn = get_db()
    conn.execute("INSERT INTO users VALUES (1, 'alice@test.com', 'Alice', 'hash', 1, '2026-10-10T00:00:00Z')")
    conn.execute("INSERT INTO membership_plans VALUES (1, 'STANDARD', 'Standard Plan', 1500, 2000, 1000, 1, '2026-10-10T00:00:00Z')")
    
    # ACTIVE with NULL member_code / qr_token must fail CHECK constraint
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO memberships VALUES (1, 1, 1, '2026-27', 'ACTIVE', '2026-08-01T00:00:00Z', '2027-08-01T00:00:00Z', NULL, NULL, NULL, NULL, NULL, '2026-10-10T00:00:00Z')")


def test_membership_expiry_must_exceed_starts_at():
    conn = get_db()
    conn.execute("INSERT INTO users VALUES (1, 'alice@test.com', 'Alice', 'hash', 1, '2026-10-10T00:00:00Z')")
    conn.execute("INSERT INTO membership_plans VALUES (1, 'STANDARD', 'Standard Plan', 1500, 2000, 1000, 1, '2026-10-10T00:00:00Z')")
    
    # expires_at <= starts_at must fail CHECK (expires_at > starts_at)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO memberships VALUES (1, 1, 1, '2026-27', 'PENDING', '2027-08-01T00:00:00Z', '2026-08-01T00:00:00Z', NULL, NULL, NULL, NULL, NULL, '2026-10-10T00:00:00Z')")


def test_membership_unique_live_per_academic_year():
    conn = get_db()
    conn.execute("INSERT INTO users VALUES (1, 'alice@test.com', 'Alice', 'hash', 1, '2026-10-10T00:00:00Z')")
    conn.execute("INSERT INTO membership_plans VALUES (1, 'STANDARD', 'Standard Plan', 1500, 2000, 1000, 1, '2026-10-10T00:00:00Z')")
    
    conn.execute("INSERT INTO memberships VALUES (1, 1, 1, '2026-27', 'ACTIVE', '2026-08-01T00:00:00Z', '2027-08-01T00:00:00Z', 'M001', 'QR001', NULL, NULL, NULL, '2026-10-10T00:00:00Z')")
    
    # Second live (PENDING or ACTIVE) membership in same year for same user must violate UNIQUE index
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO memberships VALUES (2, 1, 1, '2026-27', 'PENDING', '2026-08-01T00:00:00Z', '2027-08-01T00:00:00Z', NULL, NULL, NULL, NULL, NULL, '2026-10-10T00:00:00Z')")
