"""Unit tests for payment lifecycle, fulfillment, journal orchestration, and refunds per CONTRACT §3.1, §5, §7, §8."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any
import pytest

from clubledger.core import clock
from clubledger.core.db import apply_migrations, connect, unit_of_work
from clubledger.core.errors import DomainError
from clubledger.core.types import (
    FulfillResult,
    Handlers,
    Payment,
    PurposeHandler,
)
from clubledger.payments.service import (
    create_payment,
    expire_payments,
    handle_event,
    refund_payment,
    resolve_receipt,
    resolve_unfulfilled,
    settle_payments,
)


class MockJournal:
    def __init__(self):
        self.received_calls = []
        self.late_fulfilled_calls = []
        self.receipt_calls = []
        self.settlement_calls = []
        self.reverse_calls = []
        self.fail_on_received = False

    def post_payment_received(self, conn, payment, *, fulfilled: bool) -> int:
        if self.fail_on_received:
            raise sqlite3.IntegrityError("Injected journal failure for rollback test")
        self.received_calls.append((payment.id, fulfilled))
        return len(self.received_calls)

    def post_payment_late_fulfilled(self, conn, payment) -> int:
        self.late_fulfilled_calls.append(payment.id)
        return len(self.late_fulfilled_calls)

    def post_receipt_event(self, conn, event_row) -> int:
        self.receipt_calls.append(event_row["id"])
        return len(self.receipt_calls)

    def post_settlement(
        self, conn, source_type: str, source_id: int, amount_paise: int
    ) -> int:
        self.settlement_calls.append((source_type, source_id, amount_paise))
        return len(self.settlement_calls)

    def reverse_all_for_source(
        self, conn, source_type: str, source_id: int, memo: str
    ) -> list[int]:
        self.reverse_calls.append((source_type, source_id, memo))
        return [1]


@pytest.fixture
def test_db(tmp_path: Path):
    db_file = tmp_path / "payments_service_test.db"
    conn = connect(str(db_file))
    apply_migrations(conn)

    # Seed open term
    conn.execute(
        "INSERT INTO terms (id, label, starts_at, ends_at, status, created_at) "
        "VALUES (1, '2026-Fall', '2026-08-01T00:00:00Z', NULL, 'OPEN', '2026-08-01T00:00:00Z');"
    )
    # Seed closed term
    conn.execute(
        "INSERT INTO terms (id, label, starts_at, ends_at, status, closed_at, created_at) "
        "VALUES (2, '2026-Spring', '2026-01-01T00:00:00Z', '2026-08-01T00:00:00Z', 'CLOSED', '2026-08-01T00:00:00Z', '2026-01-01T00:00:00Z');"
    )
    # Seed active user
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (1, 'payer@example.com', 'Payer', 'hash', 1, '2026-08-01T00:00:00Z');"
    )
    # Seed inactive user
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (2, 'inactive@example.com', 'Inactive', 'hash', 0, '2026-08-01T00:00:00Z');"
    )

    conn.commit()
    conn.close()
    return str(db_file)


@pytest.fixture
def test_handlers():
    def dues_fulfill(
        conn, payment: Payment, *, manual: bool, now: str
    ) -> FulfillResult:
        return FulfillResult(outcome="FULFILLED")

    def dues_check_refund(conn, payment: Payment) -> None:
        pass

    def dues_apply_refund(conn, payment: Payment, now: str) -> None:
        pass

    dues = PurposeHandler(
        purpose="DUES",
        fulfill=dues_fulfill,
        check_refundable=dues_check_refund,
        apply_refund=dues_apply_refund,
    )

    def blocked_fulfill(
        conn, payment: Payment, *, manual: bool, now: str
    ) -> FulfillResult:
        return FulfillResult(outcome="UNFULFILLABLE", reason="SOLD_OUT")

    def blocked_check_refund(conn, payment: Payment) -> None:
        raise DomainError("REFUND_BLOCKED", 409, "Ticket already used")

    def blocked_apply_refund(conn, payment: Payment, now: str) -> None:
        pass

    ticket = PurposeHandler(
        purpose="TICKET",
        fulfill=blocked_fulfill,
        check_refundable=blocked_check_refund,
        apply_refund=blocked_apply_refund,
    )

    return {"DUES": dues, "TICKET": ticket}


def test_create_payment_validation(test_db: str):
    conn = connect(test_db)
    try:
        # Success
        p = create_payment(
            conn,
            user_id=1,
            purpose="DUES",
            ref_table="memberships",
            ref_id=10,
            amount_paise=25000,
        )
        assert p.id > 0
        assert p.status == "CREATED"
        assert p.fulfillment == "NONE"
        assert p.amount_paise == 25000
        assert p.term_id == 1

        # Non-positive amount
        with pytest.raises(DomainError) as exc:
            create_payment(
                conn,
                user_id=1,
                purpose="DUES",
                ref_table="memberships",
                ref_id=10,
                amount_paise=0,
            )
        assert exc.value.code == "VALIDATION"

        # Inactive user
        with pytest.raises(DomainError) as exc:
            create_payment(
                conn,
                user_id=2,
                purpose="DUES",
                ref_table="memberships",
                ref_id=10,
                amount_paise=25000,
            )
        assert exc.value.code == "VALIDATION"
    finally:
        conn.close()


def test_handle_event_happy_path(test_db: str, test_handlers: Handlers):
    journal = MockJournal()
    conn = connect(test_db)
    try:
        p = create_payment(
            conn,
            user_id=1,
            purpose="DUES",
            ref_table="memberships",
            ref_id=10,
            amount_paise=25000,
        )

        payload = {
            "event_id": "evt_success_1",
            "type": "payment.succeeded",
            "payment_id": p.public_id,
            "user_id": 1,
            "amount_paise": 25000,
            "currency": "INR",
        }
        raw_body = json.dumps(payload).encode("utf-8")

        outcome = handle_event(
            conn,
            handlers=test_handlers,
            raw_body=raw_body,
            signature_header="t=1,v1=abc",
            now="2026-08-01T10:00:00Z",
            journal=journal,
        )

        assert outcome.outcome == "APPLIED"
        assert outcome.reason is None
        assert outcome.payment_id == p.id

        # Verify payment updated in DB
        row = conn.execute(
            "SELECT status, fulfillment FROM payments WHERE id = ?;", (p.id,)
        ).fetchone()
        assert row["status"] == "SUCCEEDED"
        assert row["fulfillment"] == "FULFILLED"

        # Verify journal posted
        assert len(journal.received_calls) == 1
        assert journal.received_calls[0] == (p.id, True)
    finally:
        conn.close()


def test_handle_event_journal_failure_rolls_back_atomically(
    test_db: str, test_handlers: Handlers
):
    journal = MockJournal()
    journal.fail_on_received = True

    with unit_of_work(test_db) as conn:
        p = create_payment(
            conn,
            user_id=1,
            purpose="DUES",
            ref_table="memberships",
            ref_id=10,
            amount_paise=25000,
        )

    payload = {
        "event_id": "evt_fail_rollback",
        "type": "payment.succeeded",
        "payment_id": p.public_id,
        "user_id": 1,
        "amount_paise": 25000,
        "currency": "INR",
    }
    raw_body = json.dumps(payload).encode("utf-8")

    # Injected journal error rolls back the transaction
    with pytest.raises(sqlite3.IntegrityError):
        with unit_of_work(test_db) as conn:
            handle_event(
                conn,
                handlers=test_handlers,
                raw_body=raw_body,
                signature_header="t=1,v1=abc",
                now="2026-08-01T10:00:00Z",
                journal=journal,
            )

    # After rollback: payment remains CREATED, zero payment_events recorded
    conn_verify = connect(test_db)
    try:
        p_row = conn_verify.execute(
            "SELECT status, fulfillment FROM payments WHERE id = ?;", (p.id,)
        ).fetchone()
        assert p_row["status"] == "CREATED"
        assert p_row["fulfillment"] == "NONE"

        pe_count = conn_verify.execute(
            "SELECT COUNT(*) as c FROM payment_events WHERE event_id = 'evt_fail_rollback';"
        ).fetchone()["c"]
        assert pe_count == 0
    finally:
        conn_verify.close()


def test_handle_event_replay_and_conflict(test_db: str, test_handlers: Handlers):
    journal = MockJournal()
    conn = connect(test_db)
    try:
        p = create_payment(
            conn,
            user_id=1,
            purpose="DUES",
            ref_table="memberships",
            ref_id=10,
            amount_paise=25000,
        )

        payload = {
            "event_id": "evt_repeat_1",
            "type": "payment.succeeded",
            "payment_id": p.public_id,
            "user_id": 1,
            "amount_paise": 25000,
            "currency": "INR",
        }
        raw_body = json.dumps(payload).encode("utf-8")

        out1 = handle_event(
            conn,
            handlers=test_handlers,
            raw_body=raw_body,
            signature_header="t=1,v1=abc",
            now="2026-08-01T10:00:00Z",
            journal=journal,
        )
        assert out1.outcome == "APPLIED"

        # 1. Exact replay returns original outcome
        out2 = handle_event(
            conn,
            handlers=test_handlers,
            raw_body=raw_body,
            signature_header="t=1,v1=abc",
            now="2026-08-01T10:00:00Z",
            journal=journal,
        )
        assert out2.outcome == "APPLIED"
        assert out2.event_row_id == out1.event_row_id

        # 2. Changed body with same event_id raises EVENT_ID_REUSED
        conflict_payload = {
            "event_id": "evt_repeat_1",
            "type": "payment.succeeded",
            "payment_id": p.public_id,
            "user_id": 1,
            "amount_paise": 30000,  # Changed amount
            "currency": "INR",
        }
        with pytest.raises(DomainError) as exc:
            handle_event(
                conn,
                handlers=test_handlers,
                raw_body=json.dumps(conflict_payload).encode("utf-8"),
                signature_header="t=1,v1=abc",
                now="2026-08-01T10:00:00Z",
                journal=journal,
            )
        assert exc.value.code == "EVENT_ID_REUSED"
        assert exc.value.http_status == 409
    finally:
        conn.close()


def test_handle_event_repeated_notification(test_db: str, test_handlers: Handlers):
    journal = MockJournal()
    conn = connect(test_db)
    try:
        p = create_payment(
            conn,
            user_id=1,
            purpose="DUES",
            ref_table="memberships",
            ref_id=10,
            amount_paise=25000,
        )

        # First delivery
        p1 = json.dumps(
            {
                "event_id": "evt_first",
                "type": "payment.succeeded",
                "payment_id": p.public_id,
                "user_id": 1,
                "amount_paise": 25000,
                "currency": "INR",
            }
        ).encode("utf-8")
        out1 = handle_event(
            conn, test_handlers, p1, "t=1,v1=a", "2026-08-01T10:00:00Z", journal=journal
        )
        assert out1.outcome == "APPLIED"
        assert len(journal.received_calls) == 1

        # Second delivery with FRESH event_id on already paid payment -> REPEATED_NOTIFICATION / NO_EFFECT
        p2 = json.dumps(
            {
                "event_id": "evt_second",
                "type": "payment.succeeded",
                "payment_id": p.public_id,
                "user_id": 1,
                "amount_paise": 25000,
                "currency": "INR",
            }
        ).encode("utf-8")
        out2 = handle_event(
            conn, test_handlers, p2, "t=1,v1=a", "2026-08-01T10:05:00Z", journal=journal
        )
        assert out2.outcome == "NO_EFFECT"
        assert out2.reason == "REPEATED_NOTIFICATION"
        # Zero extra journal writes
        assert len(journal.received_calls) == 1
    finally:
        conn.close()


def test_handle_event_late_success_after_expired(test_db: str, test_handlers: Handlers):
    journal = MockJournal()
    conn = connect(test_db)
    try:
        p = create_payment(
            conn,
            user_id=1,
            purpose="DUES",
            ref_table="memberships",
            ref_id=10,
            amount_paise=25000,
        )
        conn.execute("UPDATE payments SET status = 'EXPIRED' WHERE id = ?;", (p.id,))

        payload = json.dumps(
            {
                "event_id": "evt_late_expired",
                "type": "payment.succeeded",
                "payment_id": p.public_id,
                "user_id": 1,
                "amount_paise": 25000,
                "currency": "INR",
            }
        ).encode("utf-8")

        out = handle_event(
            conn,
            test_handlers,
            payload,
            "t=1,v1=a",
            "2026-08-01T10:00:00Z",
            journal=journal,
        )
        assert out.outcome == "APPLIED_UNFULFILLED"
        assert out.reason == "LATE_AFTER_EXPIRED"

        p_row = conn.execute(
            "SELECT status, fulfillment FROM payments WHERE id = ?;", (p.id,)
        ).fetchone()
        assert p_row["status"] == "SUCCEEDED"
        assert p_row["fulfillment"] == "UNFULFILLED"

        # Posted to journal as unfulfilled obligation
        assert journal.received_calls[0] == (p.id, False)
    finally:
        conn.close()


def test_refund_and_resolution(test_db: str, test_handlers: Handlers):
    journal = MockJournal()
    conn = connect(test_db)
    try:
        # Create unfulfilled payment
        p = create_payment(
            conn,
            user_id=1,
            purpose="DUES",
            ref_table="memberships",
            ref_id=10,
            amount_paise=25000,
        )
        conn.execute(
            "UPDATE payments SET status = 'SUCCEEDED', fulfillment = 'UNFULFILLED' WHERE id = ?;",
            (p.id,),
        )

        # 1. Resolve via FULFILL
        resolve_unfulfilled(
            conn, test_handlers, p.id, action="FULFILL", actor_id=1, journal=journal
        )
        p_row = conn.execute(
            "SELECT fulfillment FROM payments WHERE id = ?;", (p.id,)
        ).fetchone()
        assert p_row["fulfillment"] == "FULFILLED"
        assert p.id in journal.late_fulfilled_calls

        # 2. Refund fulfilled payment
        refund_payment(conn, test_handlers, p.id, actor_id=1, journal=journal)
        p_ref = conn.execute(
            "SELECT status FROM payments WHERE id = ?;", (p.id,)
        ).fetchone()
        assert p_ref["status"] == "REFUNDED"
        assert len(journal.reverse_calls) == 1
    finally:
        conn.close()


def test_journal_failure_rolls_back_payment_and_event(
    test_db: str, test_handlers: Handlers
):
    """Regress that journal failure rolls back payment status, fulfillment, and payment_event row."""
    conn = connect(test_db)
    p = create_payment(
        conn,
        user_id=1,
        purpose="DUES",
        ref_table="memberships",
        ref_id=10,
        amount_paise=25000,
    )
    conn.close()

    payload = json.dumps(
        {
            "event_id": "evt_fail_journal",
            "type": "payment.succeeded",
            "payment_id": p.public_id,
            "user_id": 1,
            "amount_paise": 25000,
            "currency": "INR",
        }
    ).encode("utf-8")

    broken_journal = MockJournal()
    broken_journal.fail_on_received = True

    # Run in unit_of_work so transaction aborts on exception
    with pytest.raises(sqlite3.IntegrityError):
        with unit_of_work(test_db) as conn:
            handle_event(
                conn,
                handlers=test_handlers,
                raw_body=payload,
                signature_header="t=1,v1=a",
                now="2026-08-01T10:00:00Z",
                journal=broken_journal,
            )

    # Verify rollback on database: payment still CREATED/NONE, event not recorded
    conn = connect(test_db)
    try:
        p_row = conn.execute(
            "SELECT status, fulfillment FROM payments WHERE id = ?;", (p.id,)
        ).fetchone()
        assert p_row["status"] == "CREATED"
        assert p_row["fulfillment"] == "NONE"

        e_row = conn.execute(
            "SELECT 1 FROM payment_events WHERE event_id = 'evt_fail_journal';"
        ).fetchone()
        assert e_row is None
    finally:
        conn.close()


def test_missing_journal_service_raises_loudly(test_db: str, test_handlers: Handlers):
    """Ensure invalid or missing journal service methods fail loudly with DomainError."""
    conn = connect(test_db)
    try:
        p = create_payment(
            conn,
            user_id=1,
            purpose="DUES",
            ref_table="memberships",
            ref_id=10,
            amount_paise=25000,
        )
        payload = json.dumps(
            {
                "event_id": "evt_broken_journal_methods",
                "type": "payment.succeeded",
                "payment_id": p.public_id,
                "user_id": 1,
                "amount_paise": 25000,
                "currency": "INR",
            }
        ).encode("utf-8")

        class EmptyJournal:
            pass

        with pytest.raises(DomainError) as exc:
            handle_event(
                conn,
                handlers=test_handlers,
                raw_body=payload,
                signature_header="t=1,v1=a",
                now="2026-08-01T10:00:00Z",
                journal=EmptyJournal(),
            )
        assert exc.value.code == "DEPENDENCY_BLOCKER"
    finally:
        conn.close()


def test_target_expired_hold_prevents_fulfillment(
    test_db: str, test_handlers: Handlers
):
    """At callback time, an expired hold must not fulfill even if status is HELD; outcome is APPLIED_UNFULFILLED."""
    conn = connect(test_db)
    try:
        # Create an event
        conn.execute(
            """
            INSERT INTO events (
                id, term_id, title, venue, starts_at, ends_at, capacity,
                member_price_paise, public_price_paise, max_per_order, status, created_at
            ) VALUES (
                10, 1, 'Hackathon', 'Hall B', '2026-09-01T10:00:00Z', '2026-09-01T20:00:00Z',
                100, 50000, 75000, 4, 'ON_SALE', '2026-08-01T00:00:00Z'
            );
            """
        )
        # Create a ticket_hold that expired at 09:30:00Z
        conn.execute(
            """
            INSERT INTO ticket_holds (
                id, event_id, user_id, qty, unit_price_paise, price_tier,
                status, expires_at, created_at
            ) VALUES (
                50, 10, 1, 2, 75000, 'PUBLIC',
                'HELD', '2026-08-01T09:30:00Z', '2026-08-01T09:20:00Z'
            );
            """
        )
        p = create_payment(
            conn,
            user_id=1,
            purpose="TICKET",
            ref_table="ticket_holds",
            ref_id=50,
            amount_paise=150000,
        )
        conn.commit()

        journal = MockJournal()
        payload = json.dumps(
            {
                "event_id": "evt_expired_hold_success",
                "type": "payment.succeeded",
                "payment_id": p.public_id,
                "user_id": 1,
                "amount_paise": 150000,
                "currency": "INR",
            }
        ).encode("utf-8")

        # Callback arrives at 10:00:00Z (after hold expired at 09:30:00Z)
        out = handle_event(
            conn,
            handlers=test_handlers,
            raw_body=payload,
            signature_header="t=1,v1=a",
            now="2026-08-01T10:00:00Z",
            journal=journal,
        )

        assert out.outcome == "APPLIED_UNFULFILLED"
        assert out.reason == "LATE_AFTER_EXPIRED"

        p_row = conn.execute(
            "SELECT status, fulfillment FROM payments WHERE id = ?;", (p.id,)
        ).fetchone()
        assert p_row["status"] == "SUCCEEDED"
        assert p_row["fulfillment"] == "UNFULFILLED"

        # Verify no tickets were issued
        ticket_count = conn.execute(
            "SELECT count(*) FROM tickets WHERE hold_id = 50;"
        ).fetchone()[0]
        assert ticket_count == 0

        # Verify journal posted as unfulfilled (Dr 1100 / Cr 2000)
        assert len(journal.received_calls) == 1
        assert journal.received_calls[0] == (p.id, False)
    finally:
        conn.close()


def test_settled_payment_refund_reverses_all_entries(
    test_db: str, test_handlers: Handlers
):
    """Refunding a settled payment must reverse both received and settlement journal entries."""
    from clubledger.journal import service as journal_svc

    conn = connect(test_db)
    try:
        p = create_payment(
            conn,
            user_id=1,
            purpose="DUES",
            ref_table="memberships",
            ref_id=10,
            amount_paise=25000,
        )
        payload = json.dumps(
            {
                "event_id": "evt_settled_succ",
                "type": "payment.succeeded",
                "payment_id": p.public_id,
                "user_id": 1,
                "amount_paise": 25000,
                "currency": "INR",
            }
        ).encode("utf-8")

        # 1. Success event -> posts received Dr 1100 / Cr 4000
        out = handle_event(
            conn,
            test_handlers,
            payload,
            "t=1,v1=a",
            "2026-08-01T10:00:00Z",
            journal=journal_svc,
        )
        assert out.outcome == "APPLIED"

        # 2. Settle payment -> posts Dr 1000 / Cr 1100
        settled_count = settle_payments(
            conn, as_of="2026-08-03T10:00:00Z", journal=journal_svc
        )
        assert settled_count == 1

        # Check posted journal entries count for this payment (received + settlement = 2)
        cur = conn.execute(
            "SELECT count(*) FROM journal_entries WHERE source_type = 'payment' AND source_id = ? AND status = 'POSTED';",
            (p.id,),
        )
        assert cur.fetchone()[0] == 2

        # 3. Refund the settled payment
        refund_payment(conn, test_handlers, p.id, actor_id=1, journal=journal_svc)

        # Check that 2 reversal entries were posted (reversal of settlement + reversal of receipt = total 4 entries)
        cur2 = conn.execute(
            "SELECT count(*) FROM journal_entries WHERE source_type = 'payment' AND source_id = ? AND status = 'POSTED';",
            (p.id,),
        )
        assert cur2.fetchone()[0] == 4

        # Net balance on clearing 1100 must be 0
        from clubledger.reports.service import balance

        b1100 = balance(conn, "1100")
        assert b1100 == 0

        # Net balance on cash 1000 must be 0
        b1000 = balance(conn, "1000")
        assert b1000 == 0
    finally:
        conn.close()


def test_late_failed_payment_success_unfulfilled(test_db: str, test_handlers: Handlers):
    """A valid payment.succeeded after prior failure sets SUCCEEDED+UNFULFILLED and books Dr 1100 / Cr 2000."""
    from clubledger.journal import service as journal_svc

    conn = connect(test_db)
    try:
        p = create_payment(
            conn,
            user_id=1,
            purpose="DUES",
            ref_table="memberships",
            ref_id=10,
            amount_paise=25000,
        )

        # 1. Send failure event
        fail_payload = json.dumps(
            {
                "event_id": "evt_prior_fail",
                "type": "payment.failed",
                "payment_id": p.public_id,
                "user_id": 1,
                "amount_paise": 25000,
                "currency": "INR",
            }
        ).encode("utf-8")
        out_fail = handle_event(
            conn,
            test_handlers,
            fail_payload,
            "t=1,v1=a",
            "2026-08-01T10:00:00Z",
            journal=journal_svc,
        )
        assert out_fail.outcome == "APPLIED"

        p_fail = conn.execute(
            "SELECT status FROM payments WHERE id = ?;", (p.id,)
        ).fetchone()
        assert p_fail["status"] == "FAILED"

        # 2. Late success arrives
        succ_payload = json.dumps(
            {
                "event_id": "evt_late_after_fail",
                "type": "payment.succeeded",
                "payment_id": p.public_id,
                "user_id": 1,
                "amount_paise": 25000,
                "currency": "INR",
            }
        ).encode("utf-8")
        out_succ = handle_event(
            conn,
            test_handlers,
            succ_payload,
            "t=1,v1=a",
            "2026-08-01T12:00:00Z",
            journal=journal_svc,
        )
        assert out_succ.outcome == "APPLIED_UNFULFILLED"
        assert out_succ.reason == "LATE_AFTER_FAILED"

        p_row = conn.execute(
            "SELECT status, fulfillment FROM payments WHERE id = ?;", (p.id,)
        ).fetchone()
        assert p_row["status"] == "SUCCEEDED"
        assert p_row["fulfillment"] == "UNFULFILLED"

        # Check journal: 1 entry posted (Dr 1100 / Cr 2000)
        from clubledger.reports.service import balance

        b2000 = balance(conn, "2000")
        assert b2000 == 25000
    finally:
        conn.close()
