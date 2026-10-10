"""Unit tests for journal schema and journal/service.py.

Tests the early schema using an explicitly test-only subset [0001, 0006]
on a temporary SQLite database using genuine A modules (CONTRACT §1, BUILD_ORDER §1).
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
import pytest

from clubledger.core.types import Line, Payment
from clubledger.core.errors import DomainError
from clubledger.core.db import apply_migrations, unit_of_work
from clubledger.core import clock
from clubledger.journal import service


@pytest.fixture(autouse=True)
def ensure_test_env(monkeypatch):
    """Ensure CLUBLEDGER_ENV is 'test' and restore clock after each test."""
    monkeypatch.setenv("CLUBLEDGER_ENV", "test")
    clock.set_now("2026-10-10T10:00:00Z")
    yield
    clock.reset()


@pytest.fixture
def temp_db_path():
    """Provides a temporary SQLite database file with [0001, 0006] applied."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        path = tf.name

    # Apply genuine test-only migration subset [0001_core.sql, 0006_journal.sql]
    with unit_of_work(path) as conn:
        apply_migrations(
            conn,
            files=["0001_core.sql", "0006_journal.sql"],
        )
        # Seed an OPEN term
        conn.execute(
            """
            INSERT INTO terms (id, label, starts_at, status, created_at)
            VALUES (1, '2026-T1', '2026-08-01T00:00:00Z', 'OPEN', '2026-08-01T00:00:00Z')
            """
        )

    yield path

    try:
        Path(path).unlink()
    except OSError:
        pass


def test_chart_of_accounts_seeded(temp_db_path):
    with unit_of_work(temp_db_path) as conn:
        cur = conn.execute("SELECT code, type FROM accounts ORDER BY code")
        accounts = {row[0]: row[1] for row in cur.fetchall()}
        assert accounts["1000"] == "ASSET"
        assert accounts["1100"] == "ASSET"
        assert accounts["2000"] == "LIABILITY"
        assert accounts["2100"] == "LIABILITY"
        assert accounts["4000"] == "INCOME"
        assert accounts["4100"] == "INCOME"
        assert accounts["4200"] == "INCOME"
        assert accounts["5000"] == "EXPENSE"


def test_direct_posted_insert_rejected(temp_db_path):
    """Direct insert of a POSTED entry aborts via trg_entry_insert_draft_only."""
    with unit_of_work(temp_db_path) as conn:
        with pytest.raises(
            sqlite3.IntegrityError, match="Direct INSERT of POSTED entry is not allowed"
        ):
            conn.execute(
                """
                INSERT INTO journal_entries (
                    term_id, entry_date, source_type, source_id, source_event,
                    memo, status, posted_at, created_at
                ) VALUES (1, '2026-10-10T10:00:00Z', 'payment', 1, 'received', 'direct', 'POSTED', '2026-10-10T10:00:00Z', '2026-10-10T10:00:00Z')
                """
            )


def test_closed_term_insert_rejected(temp_db_path):
    """Inserting into a closed term aborts via trg_entry_insert_draft_only."""
    with unit_of_work(temp_db_path) as conn:
        conn.execute(
            """
            INSERT INTO terms (id, label, starts_at, ends_at, status, closed_at, created_at)
            VALUES (2, '2025-T2', '2025-01-01T00:00:00Z', '2025-07-31T00:00:00Z', 'CLOSED', '2025-07-31T00:00:00Z', '2025-01-01T00:00:00Z')
            """
        )
        with pytest.raises(DomainError) as excinfo:
            service.post_entry(
                conn,
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


def test_post_entry_balanced(temp_db_path):
    """Successful draft-first balanced posting under unit_of_work."""
    with unit_of_work(temp_db_path) as conn:
        entry_id = service.post_entry(
            conn,
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

        cur = conn.execute(
            "SELECT status, posted_at FROM journal_entries WHERE id = ?", (entry_id,)
        )
        status, posted_at = cur.fetchone()
        assert status == "POSTED"
        assert posted_at is not None

        cur = conn.execute(
            "SELECT COUNT(*) FROM journal_lines WHERE entry_id = ?", (entry_id,)
        )
        assert cur.fetchone()[0] == 2


def test_unbalanced_posting_rejected(temp_db_path):
    """Posting an unbalanced entry raises DomainError."""
    with unit_of_work(temp_db_path) as conn:
        with pytest.raises(DomainError) as excinfo:
            service.post_entry(
                conn,
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


def test_posted_entry_immutability(temp_db_path):
    """Triggers block updating or deleting a POSTED entry."""
    with unit_of_work(temp_db_path) as conn:
        entry_id = service.post_entry(
            conn,
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

        with pytest.raises(
            sqlite3.IntegrityError, match="POSTED journal entries are immutable"
        ):
            conn.execute(
                "UPDATE journal_entries SET memo = 'changed' WHERE id = ?", (entry_id,)
            )

        with pytest.raises(
            sqlite3.IntegrityError, match="POSTED journal entries cannot be deleted"
        ):
            conn.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))


def test_posted_lines_immutability_and_movement(temp_db_path):
    """Triggers block inserting, editing, deleting, or moving lines into/out of a POSTED entry."""
    with unit_of_work(temp_db_path) as conn:
        # Create a POSTED entry
        e_posted = service.post_entry(
            conn,
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

        # Create a DRAFT entry
        cur = conn.execute(
            """
            INSERT INTO journal_entries (
                term_id, entry_date, source_type, source_id, source_event,
                memo, status, created_at
            ) VALUES (1, '2026-10-10T10:00:00Z', 'payment', 999, 'received', 'draft', 'DRAFT', '2026-10-10T10:00:00Z')
            """
        )
        e_draft = cur.lastrowid
        cur = conn.execute(
            """
            INSERT INTO journal_lines (entry_id, account_id, debit_paise, credit_paise, created_at)
            VALUES (?, 1, 500, 0, '2026-10-10T10:00:00Z')
            """,
            (e_draft,),
        )
        draft_line_id = cur.lastrowid

        cur = conn.execute(
            "SELECT id FROM journal_lines WHERE entry_id = ?", (e_posted,)
        )
        posted_line_id = cur.fetchone()[0]

        # 1. Attempt to insert line into posted entry
        with pytest.raises(
            sqlite3.IntegrityError,
            match="Lines can only be inserted into DRAFT entries",
        ):
            conn.execute(
                """
                INSERT INTO journal_lines (entry_id, account_id, debit_paise, credit_paise, created_at)
                VALUES (?, 1, 100, 0, '2026-10-10T10:00:00Z')
                """,
                (e_posted,),
            )

        # 2. Attempt to update line in posted entry
        with pytest.raises(
            sqlite3.IntegrityError,
            match="entry_id cannot be changed|Cannot update lines of a POSTED entry",
        ):
            conn.execute(
                "UPDATE journal_lines SET debit_paise = 20000 WHERE id = ?",
                (posted_line_id,),
            )

        # 3. Attempt to delete line from posted entry
        with pytest.raises(
            sqlite3.IntegrityError, match="Cannot delete lines from a POSTED entry"
        ):
            conn.execute("DELETE FROM journal_lines WHERE id = ?", (posted_line_id,))

        # 4. Attempt to move line from posted entry into draft entry
        with pytest.raises(
            sqlite3.IntegrityError,
            match="entry_id cannot be changed|Cannot update lines of a POSTED entry",
        ):
            conn.execute(
                "UPDATE journal_lines SET entry_id = ? WHERE id = ?",
                (e_draft, posted_line_id),
            )

        # 5. Attempt to move line from draft entry into posted entry
        with pytest.raises(
            sqlite3.IntegrityError,
            match="entry_id cannot be changed|Cannot move lines into a POSTED entry",
        ):
            conn.execute(
                "UPDATE journal_lines SET entry_id = ? WHERE id = ?",
                (e_posted, draft_line_id),
            )


def test_adjusts_term_id_closed_term_enforced(temp_db_path):
    """Enforces adjusts_term_id references a CLOSED term on insert, draft update, and posting."""
    with unit_of_work(temp_db_path) as conn:
        # Term 1 is OPEN. Insert term 2 as CLOSED.
        conn.execute(
            """
            INSERT INTO terms (id, label, starts_at, ends_at, status, closed_at, created_at)
            VALUES (2, '2025-T2', '2025-01-01T00:00:00Z', '2025-07-31T00:00:00Z', 'CLOSED', '2025-07-31T00:00:00Z', '2025-01-01T00:00:00Z')
            """
        )

        # Insert with OPEN adjusts_term_id (term 1 is OPEN) fails
        with pytest.raises(
            sqlite3.IntegrityError, match="adjusts_term_id must reference a CLOSED term"
        ):
            conn.execute(
                """
                INSERT INTO journal_entries (
                    term_id, entry_date, source_type, source_id, source_event,
                    memo, status, adjusts_term_id, created_at
                ) VALUES (1, '2026-10-10T10:00:00Z', 'adjustment', 1, 'adjustment', 'adj', 'DRAFT', 1, '2026-10-10T10:00:00Z')
                """
            )

        # Insert with CLOSED adjusts_term_id (term 2) succeeds
        cur = conn.execute(
            """
            INSERT INTO journal_entries (
                term_id, entry_date, source_type, source_id, source_event,
                memo, status, adjusts_term_id, created_at
            ) VALUES (1, '2026-10-10T10:00:00Z', 'adjustment', 2, 'adjustment', 'adj', 'DRAFT', 2, '2026-10-10T10:00:00Z')
            """
        )
        draft_id = cur.lastrowid

        # Updating draft adjusts_term_id to an OPEN term (term 1) fails
        with pytest.raises(
            sqlite3.IntegrityError, match="adjusts_term_id must reference a CLOSED term"
        ):
            conn.execute(
                "UPDATE journal_entries SET adjusts_term_id = 1 WHERE id = ?",
                (draft_id,),
            )


def test_input_validation_and_idempotency_without_coercion(temp_db_path):
    """Rejects bool/non-int monetary values and strictly compares replay lines."""
    with unit_of_work(temp_db_path) as conn:
        # Rejects bool in debit/credit
        with pytest.raises(DomainError) as excinfo:
            service.post_entry(
                conn,
                term_id=1,
                entry_date="2026-10-10T10:00:00Z",
                source_type="payment",
                source_id=50,
                source_event="received",
                memo="bool amount",
                lines=[
                    Line(account_code="1100", debit_paise=True, credit_paise=0),  # type: ignore[arg-type]
                    Line(account_code="4000", debit_paise=0, credit_paise=True),  # type: ignore[arg-type]
                ],
            )
        assert excinfo.value.code == "VALIDATION"

        # Rejects string amount
        with pytest.raises(DomainError) as excinfo:
            service.post_entry(
                conn,
                term_id=1,
                entry_date="2026-10-10T10:00:00Z",
                source_type="payment",
                source_id=51,
                source_event="received",
                memo="str amount",
                lines=[
                    Line(account_code="1100", debit_paise="1000", credit_paise=0),  # type: ignore[arg-type]
                    Line(account_code="4000", debit_paise=0, credit_paise="1000"),  # type: ignore[arg-type]
                ],
            )
        assert excinfo.value.code == "VALIDATION"

        # Rejects negative amount
        with pytest.raises(DomainError) as excinfo:
            service.post_entry(
                conn,
                term_id=1,
                entry_date="2026-10-10T10:00:00Z",
                source_type="payment",
                source_id=52,
                source_event="received",
                memo="neg amount",
                lines=[
                    Line(account_code="1100", debit_paise=-100, credit_paise=0),
                    Line(account_code="4000", debit_paise=0, credit_paise=-100),
                ],
            )
        assert excinfo.value.code == "VALIDATION"

        # Valid entry
        lines = [
            Line(account_code="1100", debit_paise=15000, credit_paise=0),
            Line(account_code="4100", debit_paise=0, credit_paise=15000),
        ]
        eid1 = service.post_entry(
            conn,
            term_id=1,
            entry_date="2026-10-10T10:00:00Z",
            source_type="payment",
            source_id=105,
            source_event="received",
            memo="Ticket sold",
            lines=lines,
        )

        eid2 = service.post_entry(
            conn,
            term_id=1,
            entry_date="2026-10-10T10:00:00Z",
            source_type="payment",
            source_id=105,
            source_event="received",
            memo="Ticket sold replay",
            lines=lines,
        )
        assert eid1 == eid2

        # Conflict rejection on different amounts
        diff_lines = [
            Line(account_code="1100", debit_paise=20000, credit_paise=0),
            Line(account_code="4100", debit_paise=0, credit_paise=20000),
        ]
        with pytest.raises(DomainError) as excinfo:
            service.post_entry(
                conn,
                term_id=1,
                entry_date="2026-10-10T10:00:00Z",
                source_type="payment",
                source_id=105,
                source_event="received",
                memo="Ticket sold diff",
                lines=diff_lines,
            )
        assert excinfo.value.code == "VALIDATION"


def test_injected_failure_rolls_back_outer_unit_of_work(temp_db_path):
    """Test injected failure after DRAFT/lines rolls back the complete outer transaction."""
    with pytest.raises(RuntimeError, match="Injected failure after line insertion"):
        with unit_of_work(temp_db_path) as conn:
            # Insert draft and lines manually or via partial call
            cur = conn.execute(
                """
                INSERT INTO journal_entries (
                    term_id, entry_date, source_type, source_id, source_event,
                    memo, status, created_at
                ) VALUES (1, '2026-10-10T10:00:00Z', 'payment', 888, 'received', 'fail', 'DRAFT', '2026-10-10T10:00:00Z')
                """
            )
            draft_id = cur.lastrowid
            conn.execute(
                """
                INSERT INTO journal_lines (entry_id, account_id, debit_paise, credit_paise, created_at)
                VALUES (?, 1, 1000, 0, '2026-10-10T10:00:00Z')
                """,
                (draft_id,),
            )
            # Injected failure
            raise RuntimeError("Injected failure after line insertion")

    # Verify complete rollback
    with unit_of_work(temp_db_path) as conn:
        cur = conn.execute("SELECT COUNT(*) FROM journal_entries WHERE source_id = 888")
        assert cur.fetchone()[0] == 0
        cur = conn.execute(
            "SELECT COUNT(*) FROM journal_lines WHERE debit_paise = 1000"
        )
        assert cur.fetchone()[0] == 0


def test_payment_helpers_with_dataclass_sqlite_row_and_unknown_purpose(temp_db_path):
    """Test helpers using Payment dataclass, sqlite3.Row, and ensure unknown purpose raises VALIDATION."""
    with unit_of_work(temp_db_path) as conn:
        conn.row_factory = sqlite3.Row

        # 1. Genuine Payment dataclass
        payment_obj = Payment(
            id=701,
            public_id="pay_701",
            user_id=10,
            purpose="DUES",
            ref_table="memberships",
            ref_id=5,
            amount_paise=50000,
            status="SUCCEEDED",
            fulfillment="FULFILLED",
            term_id=1,
        )
        pid = service.post_payment_received(conn, payment_obj, fulfilled=True)
        assert pid > 0

        # 2. Unknown purpose raises VALIDATION instead of fallback
        bad_payment = Payment(
            id=702,
            public_id="pay_702",
            user_id=10,
            purpose="UNKNOWN_PURPOSE",
            ref_table="other",
            ref_id=1,
            amount_paise=50000,
            status="SUCCEEDED",
            fulfillment="FULFILLED",
            term_id=1,
        )
        with pytest.raises(DomainError) as excinfo:
            service.post_payment_received(conn, bad_payment, fulfilled=True)
        assert excinfo.value.code == "VALIDATION"

        with pytest.raises(DomainError) as excinfo:
            service.post_payment_late_fulfilled(conn, bad_payment)
        assert excinfo.value.code == "VALIDATION"

        # 3. sqlite3.Row support for event and expense
        conn.execute(
            """
            INSERT INTO users (id, email, name, password_hash, created_at)
            VALUES (1, 'u@club.org', 'User', 'hash', '2026-10-10T10:00:00Z')
            """
        )
        cur = conn.execute(
            """
            SELECT 901 as id, 25000 as amount_paise, 'INR' as currency
            """
        )
        row_event = cur.fetchone()
        assert isinstance(row_event, sqlite3.Row)
        rec_id = service.post_receipt_event(conn, row_event)
        assert rec_id > 0

        # Expense row with category_code
        cur = conn.execute(
            """
            SELECT 950 as id, 12000 as amount_paise, '5000' as category_code
            """
        )
        exp_row = cur.fetchone()
        exp_id = service.post_expense_approved(conn, exp_row)
        assert exp_id > 0


def test_reversals_exact_mirror_and_once_only(temp_db_path):
    """Reversals are exact mirrors and happen once."""
    with unit_of_work(temp_db_path) as conn:
        orig_id = service.post_entry(
            conn,
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

        rev_id = service.reverse_entry(conn, orig_id, memo="Refund payment 106")
        assert rev_id > 0
        assert rev_id != orig_id

        cur = conn.execute(
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
            service.reverse_entry(conn, orig_id, memo="Second reversal attempt")
        assert excinfo.value.code == "REFUND_BLOCKED"

        # Reversing a reversal is rejected
        with pytest.raises(DomainError) as excinfo:
            service.reverse_entry(conn, rev_id, memo="Reversing a reversal")
        assert excinfo.value.code == "REFUND_BLOCKED"


def test_reverse_all_for_source(temp_db_path):
    """reverse_all_for_source reverses all unreversed entries newest first and excludes reversals."""
    with unit_of_work(temp_db_path) as conn:
        e1 = service.post_entry(
            conn,
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
        e2 = service.post_entry(
            conn,
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

        reversed_ids = service.reverse_all_for_source(
            conn, "payment", 200, memo="Full refund"
        )
        assert len(reversed_ids) == 2
        cur = conn.execute(
            "SELECT reverses_entry_id FROM journal_entries WHERE id = ?",
            (reversed_ids[0],),
        )
        assert cur.fetchone()[0] == e2
        cur = conn.execute(
            "SELECT reverses_entry_id FROM journal_entries WHERE id = ?",
            (reversed_ids[1],),
        )
        assert cur.fetchone()[0] == e1

        retried_ids = service.reverse_all_for_source(
            conn, "payment", 200, memo="Full refund retry"
        )
        assert retried_ids == []
