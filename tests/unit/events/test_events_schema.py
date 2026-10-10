import sqlite3
from pathlib import Path
import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


def get_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    # Minimal prerequisite mock schema for foreign keys
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
    # Apply 0004_events.sql
    sql = (MIGRATIONS_DIR / "0004_events.sql").read_text(encoding="utf-8")
    conn.executescript(sql)
    return conn


def test_multi_seat_hold_and_ticket_uniqueness():
    conn = get_db()
    conn.execute("INSERT INTO users VALUES (1, 'bob@test.com', 'Bob', 'hash', 1, '2026-10-10T00:00:00Z')")
    conn.execute("INSERT INTO terms VALUES (1, 'Term 1', '2026-08-01T00:00:00Z', NULL, 'OPEN', NULL, '2026-08-01T00:00:00Z')")
    conn.execute("INSERT INTO payments VALUES (1, 'pay_evt_1', 1, 'TICKET', 'ticket_holds', 1, 1000, 'INR', 'SUCCEEDED', 'FULFILLED', 1, '2026-10-10T00:00:00Z')")
    
    conn.execute("INSERT INTO events VALUES (1, 1, 'Annual Gala', 'Main Hall', '2026-11-01T18:00:00Z', '2026-11-01T22:00:00Z', 100, 500, 800, 4, 'ON_SALE', '2026-10-10T00:00:00Z')")
    conn.execute("INSERT INTO ticket_holds VALUES (1, 1, 1, 2, 500, 'MEMBER', 'CONSUMED', '2026-10-10T01:00:00Z', NULL, '2026-10-10T00:10:00Z', '2026-10-10T00:00:00Z')")
    
    # Positive: Two distinct seats in one hold (seat_index 1 and 2)
    conn.execute("INSERT INTO tickets VALUES (1, 1, 1, 1, 1, 1, 'CODE_SEAT_1', 500, 'MEMBER', 'ISSUED', NULL, NULL, '2026-10-10T00:10:00Z')")
    conn.execute("INSERT INTO tickets VALUES (2, 1, 1, 2, 1, 1, 'CODE_SEAT_2', 500, 'MEMBER', 'ISSUED', NULL, NULL, '2026-10-10T00:10:00Z')")
    
    cur = conn.execute("SELECT count(*) FROM tickets WHERE hold_id = 1")
    assert cur.fetchone()[0] == 2
    
    # Negative: Re-inserting seat_index 1 for the same hold_id must violate UNIQUE (hold_id, seat_index)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO tickets VALUES (3, 1, 1, 1, 1, 1, 'CODE_SEAT_DUPE', 500, 'MEMBER', 'ISSUED', NULL, NULL, '2026-10-10T00:10:00Z')")


def test_ticket_paid_requires_payment_id():
    conn = get_db()
    conn.execute("INSERT INTO users VALUES (1, 'bob@test.com', 'Bob', 'hash', 1, '2026-10-10T00:00:00Z')")
    conn.execute("INSERT INTO terms VALUES (1, 'Term 1', '2026-08-01T00:00:00Z', NULL, 'OPEN', NULL, '2026-08-01T00:00:00Z')")
    conn.execute("INSERT INTO events VALUES (1, 1, 'Gala', 'Hall', '2026-11-01T18:00:00Z', '2026-11-01T22:00:00Z', 100, 500, 800, 4, 'ON_SALE', '2026-10-10T00:00:00Z')")
    conn.execute("INSERT INTO ticket_holds VALUES (1, 1, 1, 1, 500, 'MEMBER', 'CONSUMED', '2026-10-10T01:00:00Z', NULL, '2026-10-10T00:10:00Z', '2026-10-10T00:00:00Z')")
    
    # Paid ticket (price_paise = 500) with payment_id = NULL must fail CHECK
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO tickets VALUES (1, 1, 1, 1, 1, NULL, 'CODE_NO_PAY', 500, 'MEMBER', 'ISSUED', NULL, NULL, '2026-10-10T00:10:00Z')")


def test_free_ticket_allows_null_payment_id():
    conn = get_db()
    conn.execute("INSERT INTO users VALUES (1, 'bob@test.com', 'Bob', 'hash', 1, '2026-10-10T00:00:00Z')")
    conn.execute("INSERT INTO terms VALUES (1, 'Term 1', '2026-08-01T00:00:00Z', NULL, 'OPEN', NULL, '2026-08-01T00:00:00Z')")
    conn.execute("INSERT INTO events VALUES (1, 1, 'Free Seminar', 'Hall', '2026-11-01T18:00:00Z', '2026-11-01T22:00:00Z', 100, 0, 0, 4, 'ON_SALE', '2026-10-10T00:00:00Z')")
    conn.execute("INSERT INTO ticket_holds VALUES (1, 1, 1, 1, 0, 'PUBLIC', 'CONSUMED', '2026-10-10T01:00:00Z', NULL, '2026-10-10T00:10:00Z', '2026-10-10T00:00:00Z')")
    
    # Free ticket (price_paise = 0) with payment_id = NULL must succeed
    conn.execute("INSERT INTO tickets VALUES (1, 1, 1, 1, 1, NULL, 'CODE_FREE', 0, 'PUBLIC', 'ISSUED', NULL, NULL, '2026-10-10T00:10:00Z')")
    cur = conn.execute("SELECT price_paise, payment_id FROM tickets WHERE id = 1")
    assert cur.fetchone() == (0, None)


def test_ticket_used_status_requires_used_at():
    conn = get_db()
    conn.execute("INSERT INTO users VALUES (1, 'bob@test.com', 'Bob', 'hash', 1, '2026-10-10T00:00:00Z')")
    conn.execute("INSERT INTO terms VALUES (1, 'Term 1', '2026-08-01T00:00:00Z', NULL, 'OPEN', NULL, '2026-08-01T00:00:00Z')")
    conn.execute("INSERT INTO events VALUES (1, 1, 'Free Seminar', 'Hall', '2026-11-01T18:00:00Z', '2026-11-01T22:00:00Z', 100, 0, 0, 4, 'ON_SALE', '2026-10-10T00:00:00Z')")
    conn.execute("INSERT INTO ticket_holds VALUES (1, 1, 1, 1, 0, 'PUBLIC', 'CONSUMED', '2026-10-10T01:00:00Z', NULL, '2026-10-10T00:10:00Z', '2026-10-10T00:00:00Z')")
    
    # status = 'USED' but used_at IS NULL must fail CHECK ((status = 'USED') = (used_at IS NOT NULL))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO tickets VALUES (1, 1, 1, 1, 1, NULL, 'CODE_USED_NO_DATE', 0, 'PUBLIC', 'USED', NULL, NULL, '2026-10-10T00:10:00Z')")
