"""Unit tests for reports domain service (CONTRACT §11).

Tests:
  - Cumulative live balance, watermark balance, inclusive historical balance
  - Rejection of specifying both 'at' and 'watermark_id' simultaneously
  - Per-term movements
  - Cash summary and income/expense calculation
  - Rolling terms and cumulative cash not resetting
  - Reconciling entry totals and source links
  - Reconciling event ticket and journal totals separately per payment
  - Check-integrity helper
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
import pytest

from clubledger.core.types import Line, Payment
from clubledger.core.errors import DomainError
from clubledger.core.db import apply_migrations, unit_of_work
from clubledger.core import clock
from clubledger.journal import service as journal_service
from clubledger.reports import service as reports_service


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    monkeypatch.setenv("CLUBLEDGER_ENV", "test")
    clock.set_now("2026-10-10T10:00:00Z")
    yield
    clock.reset()


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        path = tf.name

    with unit_of_work(path) as conn:
        # Apply 0001_core.sql, 0002_payments.sql, 0006_journal.sql
        apply_migrations(conn, files=["0001_core.sql", "0002_payments.sql", "0006_journal.sql"])

        # Also create events and tickets tables to test event reconciliation
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY,
              term_id INTEGER NOT NULL REFERENCES terms(id),
              title TEXT NOT NULL, venue TEXT NOT NULL, starts_at TEXT NOT NULL, ends_at TEXT NOT NULL,
              capacity INTEGER NOT NULL, member_price_paise INTEGER NOT NULL, public_price_paise INTEGER NOT NULL,
              status TEXT NOT NULL, created_at TEXT NOT NULL
            ) STRICT;

            CREATE TABLE IF NOT EXISTS ticket_holds (
              id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
              qty INTEGER NOT NULL, unit_price_paise INTEGER NOT NULL, price_tier TEXT NOT NULL,
              status TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL
            ) STRICT;

            CREATE TABLE IF NOT EXISTS tickets (
              id INTEGER PRIMARY KEY,
              event_id INTEGER NOT NULL,
              hold_id INTEGER NOT NULL,
              seat_index INTEGER NOT NULL,
              user_id INTEGER NOT NULL,
              payment_id INTEGER,
              code TEXT NOT NULL UNIQUE,
              price_paise INTEGER NOT NULL,
              price_tier TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL
            ) STRICT;
            """
        )

        # Seed users and terms
        conn.execute(
            """
            INSERT INTO users (id, email, name, password_hash, is_active, created_at)
            VALUES (1, 'u@club.org', 'Alice', 'scrypt$hash', 1, '2026-08-01T00:00:00Z')
            """
        )
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


def test_balance_cutoffs_and_rejections(db_path):
    """Test live, watermark, and historical cutoffs and reject using both at and watermark."""
    with unit_of_work(db_path) as conn:
        # Post entry 1 at T1
        clock.set_now("2026-10-10T10:00:00Z")
        e1 = journal_service.post_entry(
            conn,
            term_id=1,
            entry_date="2026-10-10T10:00:00Z",
            source_type="payment",
            source_id=1,
            source_event="received",
            memo="Entry 1",
            lines=[
                Line(account_code="1100", debit_paise=10000, credit_paise=0),
                Line(account_code="4000", debit_paise=0, credit_paise=10000),
            ],
        )

        # Post entry 2 at same second T1 (same-second live posting)
        e2 = journal_service.post_entry(
            conn,
            term_id=1,
            entry_date="2026-10-10T10:00:00Z",
            source_type="payment",
            source_id=2,
            source_event="received",
            memo="Entry 2",
            lines=[
                Line(account_code="1100", debit_paise=5000, credit_paise=0),
                Line(account_code="4000", debit_paise=0, credit_paise=5000),
            ],
        )

        # Post entry 3 at T2
        clock.set_now("2026-10-10T12:00:00Z")
        e3 = journal_service.post_entry(
            conn,
            term_id=1,
            entry_date="2026-10-10T12:00:00Z",
            source_type="payment",
            source_id=3,
            source_event="received",
            memo="Entry 3",
            lines=[
                Line(account_code="1100", debit_paise=3000, credit_paise=0),
                Line(account_code="4000", debit_paise=0, credit_paise=3000),
            ],
        )

        # 1. Live balance includes all 3 entries (18000)
        assert reports_service.balance(conn, "1100") == 18000
        assert reports_service.balance(conn, "4000") == 18000

        # 2. Watermark balance (id <= e1 excludes e2 and e3 even though e2 shares timestamp)
        assert reports_service.balance(conn, "1100", watermark_id=e1) == 10000
        assert reports_service.balance(conn, "1100", watermark_id=e2) == 15000

        # 3. Inclusive historical balance (at <= 10:00:00Z includes both e1 and e2)
        assert reports_service.balance(conn, "1100", at="2026-10-10T10:00:00Z") == 15000
        assert reports_service.balance(conn, "1100", at="2026-10-10T09:00:00Z") == 0

        # 4. Reject specifying both at and watermark_id
        with pytest.raises(DomainError) as excinfo:
            reports_service.balance(conn, "1100", at="2026-10-10T10:00:00Z", watermark_id=e1)
        assert excinfo.value.code == "VALIDATION"


def test_cumulative_cash_across_terms(db_path):
    """Test that rolling terms do not reset cumulative cash on hand."""
    with unit_of_work(db_path) as conn:
        # In term 1: receive payment 10000 into clearing, then settle to cash
        journal_service.post_entry(
            conn,
            term_id=1,
            entry_date="2026-08-10T10:00:00Z",
            source_type="payment",
            source_id=10,
            source_event="received",
            memo="Term 1 payment",
            lines=[
                Line(account_code="1100", debit_paise=10000, credit_paise=0),
                Line(account_code="4000", debit_paise=0, credit_paise=10000),
            ],
        )
        journal_service.post_settlement(conn, "payment", 10, 10000)

        # Cash balance in term 1
        assert reports_service.balance(conn, "1000") == 10000
        assert reports_service.balance(conn, "1100") == 0

        # Close term 1 and open term 2
        conn.execute(
            """
            UPDATE terms
            SET status = 'CLOSED', ends_at = '2026-12-31T23:59:59Z', closed_at = '2026-12-31T23:59:59Z'
            WHERE id = 1
            """
        )
        conn.execute(
            """
            INSERT INTO terms (id, label, starts_at, status, created_at)
            VALUES (2, '2027-T1', '2026-12-31T23:59:59Z', 'OPEN', '2026-12-31T23:59:59Z')
            """
        )

        # In term 2: cash must still be 10000 (cumulative)
        cs = reports_service.cash_summary(conn, 2)
        assert cs.cash_on_hand == 10000
        assert cs.in_clearing == 0

        # Term 2 movement of 1000 is 0
        mov = reports_service.movement(conn, "1000", 2)
        assert mov.debit_paise == 0 and mov.credit_paise == 0

        # New activity in term 2
        journal_service.post_entry(
            conn,
            term_id=2,
            entry_date="2027-01-05T10:00:00Z",
            source_type="payment",
            source_id=20,
            source_event="received",
            memo="Term 2 payment",
            lines=[
                Line(account_code="1100", debit_paise=7000, credit_paise=0),
                Line(account_code="4000", debit_paise=0, credit_paise=7000),
            ],
        )
        cs2 = reports_service.cash_summary(conn, 2)
        assert cs2.cash_on_hand == 10000
        assert cs2.in_clearing == 7000

        # Income/expense for term 2 only reflects term 2 income
        ie = reports_service.income_expense(conn, 2)
        assert ie.accounts["4000"] == 7000
        assert ie.net_surplus == 7000


def test_acceptance_flow_dues_ticket_sale_settlement(db_path):
    """Verify acceptance criterion:

    After dues and a ticket sale:
      - clearing equals both received amounts
      - each journal entry balances
      - ticket proceeds match ticket prices
      - drilldown sums match report totals
      - settlement transfers clearing to cash without creating income again.
    """
    with unit_of_work(db_path) as conn:
        # Create payment rows in payments table
        conn.execute(
            """
            INSERT INTO payments (id, public_id, user_id, purpose, ref_table, ref_id, amount_paise, status, fulfillment, term_id, created_at)
            VALUES (101, 'pay_dues', 1, 'DUES', 'memberships', 1, 50000, 'SUCCEEDED', 'FULFILLED', 1, '2026-10-10T10:00:00Z'),
                   (102, 'pay_ticket', 1, 'TICKET', 'ticket_holds', 1, 40000, 'SUCCEEDED', 'FULFILLED', 1, '2026-10-10T10:05:00Z')
            """
        )

        # Create multi-ticket rows for payment 102 (e.g. 2 tickets at 20000 each = 40000 total)
        conn.execute(
            """
            INSERT INTO tickets (id, event_id, hold_id, seat_index, user_id, payment_id, code, price_paise, price_tier, status, created_at)
            VALUES (1, 1, 1, 1, 1, 102, 'TICK1', 20000, 'MEMBER', 'ISSUED', '2026-10-10T10:05:00Z'),
                   (2, 1, 1, 2, 1, 102, 'TICK2', 20000, 'MEMBER', 'USED', '2026-10-10T10:05:00Z')
            """
        )

        # 1. Post Dues Payment Received (50000)
        p1 = Payment(101, "pay_dues", 1, "DUES", "memberships", 1, 50000, "SUCCEEDED", "FULFILLED", 1)
        journal_service.post_payment_received(conn, p1, fulfilled=True)

        # 2. Post Ticket Payment Received (40000)
        p2 = Payment(102, "pay_ticket", 1, "TICKET", "ticket_holds", 1, 40000, "SUCCEEDED", "FULFILLED", 1)
        journal_service.post_payment_received(conn, p2, fulfilled=True)

        # Clearing equals both received amounts (50000 + 40000 = 90000)
        cs = reports_service.cash_summary(conn, 1)
        assert cs.in_clearing == 90000
        assert cs.cash_on_hand == 0

        # Ticket proceeds match ticket prices via separate aggregation
        j_net, t_sum = reports_service.reconcile_payment_event_journal(conn, 102)
        assert j_net == 40000
        assert t_sum == 40000
        assert j_net == t_sum

        # Drilldown totals match
        dd_clearing = reports_service.drilldown(conn, account_code="1100")
        assert dd_clearing.total_paise == 90000
        assert len(dd_clearing.items) == 2

        # 3. Settle Dues (50000)
        journal_service.post_settlement(conn, "payment", 101, 50000)

        # Clearing drops by 50000, cash rises by 50000
        cs_after_settle = reports_service.cash_summary(conn, 1)
        assert cs_after_settle.in_clearing == 40000
        assert cs_after_settle.cash_on_hand == 50000

        # Income has NOT increased again (remains 50000 dues + 40000 tickets = 90000)
        assert reports_service.balance(conn, "4000") == 50000
        assert reports_service.balance(conn, "4100") == 40000

        # Integrity check passes
        chk = reports_service.check_integrity(conn)
        assert chk["passed"] is True
        assert chk["checks"]["debits_equal_credits"]["status"] == "PASS"
        assert chk["checks"]["succeeded_payments_received_entry"]["status"] == "PASS"
        assert chk["checks"]["event_ticket_journal_reconciliation"]["status"] == "PASS"


def test_missing_source_fails_integrity(db_path):
    """A journal entry pointing to a non-existent payment fails integrity check."""
    with unit_of_work(db_path) as conn:
        journal_service.post_entry(
            conn,
            term_id=1,
            entry_date="2026-10-10T10:00:00Z",
            source_type="payment",
            source_id=99999,  # Non-existent payment id
            source_event="received",
            memo="Ghost payment entry",
            lines=[
                Line(account_code="1100", debit_paise=1000, credit_paise=0),
                Line(account_code="4000", debit_paise=0, credit_paise=1000),
            ],
        )

        chk = reports_service.check_integrity(conn)
        assert chk["passed"] is False
        assert "source_links_integrity" in chk["failures"]
        assert chk["checks"]["source_links_integrity"]["status"] == "FAIL"
