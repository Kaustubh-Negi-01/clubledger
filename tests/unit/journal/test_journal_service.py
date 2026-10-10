"""Unit tests for journal schema and journal/service.py.

Tests the early schema using an explicitly test-only subset [0001, 0006]
on a temporary SQLite database (CONTRACT §1, BUILD_ORDER §1).
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
import pytest

from clubledger.journal.service import (
    Line,
    DomainError,
    clock,
    post_entry,
    reverse_entry,
    reverse_all_for_source,
    post_payment_received,
    post_payment_late_fulfilled,
    post_receipt_event,
    post_settlement,
)


CORE_0001_SQL = """
CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  created_at TEXT NOT NULL
) STRICT;

CREATE TABLE terms (
  id INTEGER PRIMARY KEY,
  label TEXT NOT NULL UNIQUE,
  starts_at TEXT NOT NULL,
  ends_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('OPEN','CLOSED')),
  closed_at TEXT,
  created_at TEXT NOT NULL,
  CHECK ((status = 'OPEN' AND ends_at IS NULL AND closed_at IS NULL)
      OR (status = 'CLOSED' AND ends_at IS NOT NULL AND closed_at IS NOT NULL AND ends_at > starts_at))
) STRICT;
CREATE UNIQUE INDEX ux_terms_one_open ON terms(status) WHERE status = 'OPEN';
"""


@pytest.fixture
def db_conn():
    """Sets up an in-memory/temp SQLite db with [0001, 0006] applied."""
    clock.now = lambda: "2026-10-10T10:00:00Z"

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")

    # Apply 0001 subset (users, terms)
    conn.executescript(CORE_0001_SQL)

    # Read and apply 0006_journal.sql
    migration_file = Path(__file__).resolve().parents[3] / "clubledger" / "migrations" / "0006_journal.sql"
    conn.executescript(migration_file.read_text(encoding="utf-8"))

    # Seed an open term
    conn.execute(
        """
        INSERT INTO terms (id, label, starts_at, status, created_at)
        VALUES (1, '2026-T1', '2026-08-01T00:00:00Z', 'OPEN', '2026-08-01T00:00:00Z')
        """
    )
    conn.commit()

    try:
        yield conn
    finally:
        conn.close()
        try:
            Path(db_path).unlink()
        except OSError:
            pass


def test_chart_of_accounts_seeded(db_conn):
    cur = db_conn.execute("SELECT code, type FROM accounts ORDER BY code")
    accounts = {row[0]: row[1] for row in cur.fetchall()}
    assert "1000" in accounts and accounts["1000"] == "ASSET"
    assert "1100" in accounts and accounts["1100"] == "ASSET"
    assert "2000" in accounts and accounts["2000"] == "LIABILITY"
    assert "2100" in accounts and accounts["2100"] == "LIABILITY"
    assert "4000" in accounts and accounts["4000"] == "INCOME"
    assert "4100" in accounts and accounts["4100"] == "INCOME"
    assert "4200" in accounts and accounts["4200"] == "INCOME"
    assert "5000" in accounts and accounts["5000"] == "EXPENSE"


def test_direct_posted_insert_rejected(db_conn):
    """Direct insert of a POSTED entry aborts via trg_entry_insert_draft_only."""
    with pytest.raises(sqlite3.IntegrityError, match="Direct INSERT of POSTED entry is not allowed"):
        db_conn.execute(
            """
            INSERT INTO journal_entries (
                term_id, entry_date, source_type, source_id, source_event,
                memo, status, posted_at, created_at
            ) VALUES (1, '2026-10-10T10:00:00Z', 'payment', 1, 'received', 'direct', 'POSTED', '2026-10-10T10:00:00Z', '2026-10-10T10:00:00Z')
            """
        )


def test_closed_term_insert_rejected(db_conn):
    """Inserting into a closed term aborts via trg_entry_insert_draft_only."""
    # Insert a closed term
    db_conn.execute(
        """
        INSERT INTO terms (id, label, starts_at, ends_at, status, closed_at, created_at)
        VALUES (2, '2025-T2', '2025-01-01T00:00:00Z', '2025-07-31T00:00:00Z', 'CLOSED', '2025-07-31T00:00:00Z', '2025-01-01T00:00:00Z')
        """
    )
    with pytest.raises(DomainError) as excinfo:
        post_entry(
            db_conn,
            term_id=2,
            entry_date="2026-10-10T10:00:00Z",
            source_type="payment",
            source_id=1,
            source_event="received",
            memo="test",
            lines=[
                Line(account_code="1100", debit_paise=100, credit_paise=0),
                Line(account_code="4000", debit_paise=0, credit_paise=100),
            ],
        )
    assert excinfo.value.code == "TERM_CLOSED"


def test_post_entry_balanced(db_conn):
    """Successful draft-first balanced posting."""
    entry_id = post_entry(
        db_conn,
        term_id=1,
        entry_date="2026-10-10T10:00:00Z",
        source_type="payment",
        source_id=101,
        source_event="received",
        memo="Dues received",
        lines=[
            Line(account_code="1100", debit_paise=50000, credit_paise=0),
            Line(account_code="4000", debit_paise=0, credit_paise=50000),
        ],
    )
    assert entry_id > 0

    cur = db_conn.execute("SELECT status, posted_at FROM journal_entries WHERE id = ?", (entry_id,))
    status, posted_at = cur.fetchone()
    assert status == "POSTED"
    assert posted_at is not None

    cur = db_conn.execute("SELECT COUNT(*) FROM journal_lines WHERE entry_id = ?", (entry_id,))
    assert cur.fetchone()[0] == 2


def test_unbalanced_posting_rejected(db_conn):
    """Posting an unbalanced entry raises DomainError."""
    with pytest.raises(DomainError) as excinfo:
        post_entry(
            db_conn,
            term_id=1,
            entry_date="2026-10-10T10:00:00Z",
            source_type="payment",
            source_id=102,
            source_event="received",
            memo="Unbalanced",
            lines=[
                Line(account_code="1100", debit_paise=50000, credit_paise=0),
                Line(account_code="4000", debit_paise=0, credit_paise=40000),
            ],
        )
    assert excinfo.value.code == "VALIDATION"


def test_posted_entry_immutability(db_conn):
    """Triggers block updating or deleting a POSTED entry."""
    entry_id = post_entry(
        db_conn,
        term_id=1,
        entry_date="2026-10-10T10:00:00Z",
        source_type="payment",
        source_id=103,
        source_event="received",
        memo="Immutability check",
        lines=[
            Line(account_code="1100", debit_paise=25000, credit_paise=0),
            Line(account_code="4000", debit_paise=0, credit_paise=25000),
        ],
    )

    # Attempt to update memo of posted entry
    with pytest.raises(sqlite3.IntegrityError, match="POSTED journal entries are immutable"):
        db_conn.execute("UPDATE journal_entries SET memo = 'changed' WHERE id = ?", (entry_id,))

    # Attempt to delete posted entry
    with pytest.raises(sqlite3.IntegrityError, match="POSTED journal entries cannot be deleted"):
        db_conn.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))


def test_posted_lines_immutability(db_conn):
    """Triggers block inserting, editing, deleting, or moving lines of a POSTED entry."""
    entry_id = post_entry(
        db_conn,
        term_id=1,
        entry_date="2026-10-10T10:00:00Z",
        source_type="payment",
        source_id=104,
        source_event="received",
        memo="Lines check",
        lines=[
            Line(account_code="1100", debit_paise=10000, credit_paise=0),
            Line(account_code="4000", debit_paise=0, credit_paise=10000),
        ],
    )

    cur = db_conn.execute("SELECT id FROM journal_lines WHERE entry_id = ?", (entry_id,))
    line_id = cur.fetchone()[0]

    # Attempt to insert new line into posted entry
    with pytest.raises(sqlite3.IntegrityError, match="Lines can only be inserted into DRAFT entries"):
        db_conn.execute(
            """
            INSERT INTO journal_lines (entry_id, account_id, debit_paise, credit_paise, created_at)
            VALUES (?, 1, 100, 0, '2026-10-10T10:00:00Z')
            """,
            (entry_id,),
        )

    # Attempt to edit line
    with pytest.raises(sqlite3.IntegrityError, match="Cannot update lines of a POSTED entry"):
        db_conn.execute("UPDATE journal_lines SET debit_paise = 20000 WHERE id = ?", (line_id,))

    # Attempt to delete line
    with pytest.raises(sqlite3.IntegrityError, match="Cannot delete lines from a POSTED entry"):
        db_conn.execute("DELETE FROM journal_lines WHERE id = ?", (line_id,))


def test_idempotent_posting_and_conflict_rejection(db_conn):
    """Repeated posting with identical content returns existing id; different content raises."""
    lines = [
        Line(account_code="1100", debit_paise=15000, credit_paise=0),
        Line(account_code="4100", debit_paise=0, credit_paise=15000),
    ]

    id1 = post_entry(
        db_conn,
        term_id=1,
        entry_date="2026-10-10T10:00:00Z",
        source_type="payment",
        source_id=105,
        source_event="received",
        memo="Ticket sold",
        lines=lines,
    )

    # Identical replay returns same id
    id2 = post_entry(
        db_conn,
        term_id=1,
        entry_date="2026-10-10T10:00:00Z",
        source_type="payment",
        source_id=105,
        source_event="received",
        memo="Ticket sold",
        lines=lines,
    )
    assert id1 == id2

    # Different financial content raises VALIDATION
    different_lines = [
        Line(account_code="1100", debit_paise=20000, credit_paise=0),
        Line(account_code="4100", debit_paise=0, credit_paise=20000),
    ]
    with pytest.raises(DomainError) as excinfo:
        post_entry(
            db_conn,
            term_id=1,
            entry_date="2026-10-10T10:00:00Z",
            source_type="payment",
            source_id=105,
            source_event="received",
            memo="Ticket sold different money",
            lines=different_lines,
        )
    assert excinfo.value.code == "VALIDATION"


def test_reversals_exact_mirror_and_once_only(db_conn):
    """Reversals are exact mirrors and happen once."""
    orig_id = post_entry(
        db_conn,
        term_id=1,
        entry_date="2026-10-10T10:00:00Z",
        source_type="payment",
        source_id=106,
        source_event="received",
        memo="Initial entry",
        lines=[
            Line(account_code="1100", debit_paise=12000, credit_paise=0),
            Line(account_code="4000", debit_paise=0, credit_paise=12000),
        ],
    )

    rev_id = reverse_entry(db_conn, orig_id, memo="Refund payment 106")
    assert rev_id > 0
    assert rev_id != orig_id

    # Verify mirror lines
    cur = db_conn.execute(
        """
        SELECT a.code, jl.debit_paise, jl.credit_paise
        FROM journal_lines jl
        JOIN accounts a ON a.id = jl.account_id
        WHERE jl.entry_id = ?
        ORDER BY a.code
        """,
        (rev_id,),
    )
    rev_lines = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    assert rev_lines["1100"] == (0, 12000)
    assert rev_lines["4000"] == (12000, 0)

    # Reversing twice raises REFUND_BLOCKED
    with pytest.raises(DomainError) as excinfo:
        reverse_entry(db_conn, orig_id, memo="Second reversal attempt")
    assert excinfo.value.code == "REFUND_BLOCKED"

    # Reversing a reversal is rejected
    with pytest.raises(DomainError) as excinfo:
        reverse_entry(db_conn, rev_id, memo="Reversing a reversal")
    assert excinfo.value.code == "REFUND_BLOCKED"


def test_reverse_all_for_source(db_conn):
    """reverse_all_for_source reverses all unreversed entries newest first and excludes reversals."""
    e1 = post_entry(
        db_conn,
        term_id=1,
        entry_date="2026-10-10T10:00:00Z",
        source_type="payment",
        source_id=200,
        source_event="received",
        memo="Received",
        lines=[
            Line(account_code="1100", debit_paise=5000, credit_paise=0),
            Line(account_code="2000", debit_paise=0, credit_paise=5000),
        ],
    )
    e2 = post_entry(
        db_conn,
        term_id=1,
        entry_date="2026-10-10T10:01:00Z",
        source_type="payment",
        source_id=200,
        source_event="fulfilled_late",
        memo="Fulfilled late",
        lines=[
            Line(account_code="2000", debit_paise=5000, credit_paise=0),
            Line(account_code="4000", debit_paise=0, credit_paise=5000),
        ],
    )

    reversed_ids = reverse_all_for_source(db_conn, "payment", 200, memo="Full refund")
    assert len(reversed_ids) == 2
    # Verify newest first reversal order
    cur = db_conn.execute("SELECT reverses_entry_id FROM journal_entries WHERE id = ?", (reversed_ids[0],))
    assert cur.fetchone()[0] == e2
    cur = db_conn.execute("SELECT reverses_entry_id FROM journal_entries WHERE id = ?", (reversed_ids[1],))
    assert cur.fetchone()[0] == e1

    # Retry should reverse nothing since all are already reversed
    retried_ids = reverse_all_for_source(db_conn, "payment", 200, memo="Full refund retry")
    assert retried_ids == []


def test_payment_and_settlement_posting_helpers(db_conn):
    """Test payment received, fulfilled_late, unapplied receipt, and settlement posting."""
    # 1. Fulfilled payment received
    payment = {"id": 301, "amount_paise": 60000, "purpose": "DUES"}
    pid = post_payment_received(db_conn, payment, fulfilled=True)
    assert pid > 0

    # 2. Unfulfilled payment received
    payment_unf = {"id": 302, "amount_paise": 35000, "purpose": "TICKET"}
    p_unf_id = post_payment_received(db_conn, payment_unf, fulfilled=False)
    assert p_unf_id > 0

    # 3. Late fulfillment
    late_id = post_payment_late_fulfilled(db_conn, payment_unf)
    assert late_id > 0

    # 4. Settlement
    settle_id = post_settlement(db_conn, "payment", 301, 60000)
    assert settle_id > 0

    # 5. Receipt event
    event_row = {"id": 401, "amount_paise": 10000, "currency": "INR"}
    rec_id = post_receipt_event(db_conn, event_row)
    assert rec_id is not None and rec_id > 0

    # Non-INR receipt event returns None
    event_usd = {"id": 402, "amount_paise": 10000, "currency": "USD"}
    assert post_receipt_event(db_conn, event_usd) is None
