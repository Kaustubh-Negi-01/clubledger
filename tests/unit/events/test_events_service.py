"""Unit tests for events and ticketing service per CONTRACT.md §1.4, §2, §3.3, §13.3."""

import sqlite3
import pytest

from clubledger.core import clock
from clubledger.core.db import apply_migrations, connect
from clubledger.core.errors import DomainError
from clubledger.core.types import Payment
from clubledger.events.service import (
    TICKET_PURPOSE_HANDLER,
    DependencyBlockerError,
    apply_refund_tickets,
    cancel_event,
    check_in,
    check_refundable_tickets,
    create_hold,
    event_report,
    expire_holds,
    fulfill_ticket_hold,
    get_available_seats,
    seed_events,
)


def mock_create_payment(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    purpose: str,
    ref_table: str,
    ref_id: int,
    amount_paise: int,
) -> Payment:
    """Mock payment creation for testing paid hold workflows."""
    term_row = conn.execute("SELECT id FROM terms WHERE status = 'OPEN' LIMIT 1;").fetchone()
    term_id = term_row["id"] if term_row else 1
    cur = conn.execute(
        "INSERT INTO payments (public_id, user_id, purpose, ref_table, ref_id, amount_paise, currency, status, fulfillment, term_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'INR', 'CREATED', 'NONE', ?, ?);",
        (f"pay_hold_{ref_id}", user_id, purpose, ref_table, ref_id, amount_paise, term_id, clock.now()),
    )
    return Payment(
        id=cur.lastrowid,  # type: ignore
        public_id=f"pay_hold_{ref_id}",
        user_id=user_id,
        purpose=purpose,
        ref_table=ref_table,
        ref_id=ref_id,
        amount_paise=amount_paise,
        status="CREATED",
        fulfillment="NONE",
        term_id=term_id,
    )


@pytest.fixture
def db_conn(monkeypatch):
    monkeypatch.setenv("CLUBLEDGER_ENV", "test")
    clock.set_now("2026-10-10T10:00:00Z")
    conn = connect(":memory:")
    apply_migrations(conn)

    # Seed base term
    conn.execute(
        "INSERT INTO terms (id, label, starts_at, ends_at, status, closed_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?);",
        (1, "Term 2026-27", "2026-08-01T00:00:00Z", None, "OPEN", None, "2026-08-01T00:00:00Z"),
    )

    # Seed users
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (?, ?, ?, ?, 1, ?);",
        (1, "alice@test.com", "Alice Member", "scrypt_hash", "2026-10-10T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (?, ?, ?, ?, 1, ?);",
        (2, "bob@test.com", "Bob Public", "scrypt_hash", "2026-10-10T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (?, ?, ?, ?, 1, ?);",
        (3, "staff@test.com", "Staff Member", "scrypt_hash", "2026-10-10T00:00:00Z"),
    )

    # Seed membership plan and active membership for Alice
    conn.execute(
        "INSERT INTO membership_plans (id, code, name, dues_paise, ticket_discount_bps, merch_discount_bps, is_active, created_at) "
        "VALUES (1, 'annual_std', 'Standard Plan', 50000, 2000, 1000, 1, '2026-10-10T00:00:00Z');"
    )
    conn.execute(
        "INSERT INTO memberships (id, user_id, plan_id, membership_year, status, starts_at, expires_at, member_code, qr_token, created_at) "
        "VALUES (1, 1, 1, '2026-27', 'ACTIVE', '2026-08-01T00:00:00Z', '2027-07-31T23:59:59Z', 'MEM-ALICE', 'QR-ALICE', '2026-10-10T00:00:00Z');"
    )

    # Seed events
    # Event 1: Paid Gala (capacity 10, member 80000 paise, public 100000 paise, max 4 per order)
    conn.execute(
        "INSERT INTO events (id, term_id, title, venue, starts_at, ends_at, capacity, member_price_paise, public_price_paise, max_per_order, status, created_at) "
        "VALUES (1, 1, 'Gala', 'Main Hall', '2026-11-01T18:00:00Z', '2026-11-01T22:00:00Z', 10, 80000, 100000, 4, 'ON_SALE', '2026-10-10T00:00:00Z');"
    )
    # Event 2: Free Workshop (capacity 2, member 0 paise, public 0 paise, max 2 per order)
    conn.execute(
        "INSERT INTO events (id, term_id, title, venue, starts_at, ends_at, capacity, member_price_paise, public_price_paise, max_per_order, status, created_at) "
        "VALUES (2, 1, 'Free Workshop', 'Lab 1', '2026-11-02T10:00:00Z', '2026-11-02T12:00:00Z', 2, 0, 0, 2, 'ON_SALE', '2026-10-10T00:00:00Z');"
    )

    yield conn
    conn.close()


def test_create_hold_paid_member_vs_public(db_conn):
    # Member Alice gets member price
    hold_alice, pay_alice = create_hold(
        db_conn,
        user_id=1,
        event_id=1,
        qty=2,
        idempotency_key="idemp_alice_1",
        create_payment_fn=mock_create_payment,
    )
    assert hold_alice.unit_price_paise == 80000
    assert hold_alice.price_tier == "MEMBER"
    assert hold_alice.status == "HELD"
    assert pay_alice is not None
    assert pay_alice.amount_paise == 160000

    # Non-member Bob gets public price
    hold_bob, pay_bob = create_hold(
        db_conn,
        user_id=2,
        event_id=1,
        qty=1,
        idempotency_key="idemp_bob_1",
        create_payment_fn=mock_create_payment,
    )
    assert hold_bob.unit_price_paise == 100000
    assert hold_bob.price_tier == "PUBLIC"
    assert pay_bob is not None
    assert pay_bob.amount_paise == 100000


def test_create_hold_free_tickets(db_conn):
    # Free tickets bypass payment, hold is immediately CONSUMED and tickets are ISSUED
    hold, payment = create_hold(
        db_conn,
        user_id=1,
        event_id=2,
        qty=2,
        idempotency_key="idemp_free_1",
    )
    assert payment is None
    assert hold.status == "CONSUMED"
    assert hold.unit_price_paise == 0

    tickets = db_conn.execute("SELECT * FROM tickets WHERE hold_id = ? ORDER BY seat_index ASC;", (hold.id,)).fetchall()
    assert len(tickets) == 2
    assert tickets[0]["seat_index"] == 1
    assert tickets[1]["seat_index"] == 2
    assert tickets[0]["payment_id"] is None
    assert tickets[0]["status"] == "ISSUED"
    assert tickets[0]["code"].startswith("TKT-")


def test_capacity_safe_oversell_prevention(db_conn):
    # Event 2 has capacity 2. Alice reserves 2 seats.
    create_hold(
        db_conn,
        user_id=1,
        event_id=2,
        qty=2,
        idempotency_key="idemp_take_all",
    )

    # Bob tries to reserve 1 seat -> SOLD_OUT 409
    with pytest.raises(DomainError) as exc_info:
        create_hold(
            db_conn,
            user_id=2,
            event_id=2,
            qty=1,
            idempotency_key="idemp_bob_fail",
        )
    assert exc_info.value.code == "SOLD_OUT"
    assert exc_info.value.http_status == 409


def test_quantity_limits_validation(db_conn):
    # Qty 0 or qty > max_per_order (Event 1 max is 4)
    with pytest.raises(DomainError) as exc1:
        create_hold(db_conn, 1, 1, 0, "k1", create_payment_fn=mock_create_payment)
    assert exc1.value.code == "VALIDATION"

    with pytest.raises(DomainError) as exc2:
        create_hold(db_conn, 1, 1, 5, "k2", create_payment_fn=mock_create_payment)
    assert exc2.value.code == "VALIDATION"


def test_hold_idempotency_replay(db_conn):
    hold1, pay1 = create_hold(
        db_conn,
        user_id=1,
        event_id=1,
        qty=2,
        idempotency_key="idemp_same_key",
        create_payment_fn=mock_create_payment,
    )
    hold2, pay2 = create_hold(
        db_conn,
        user_id=1,
        event_id=1,
        qty=2,
        idempotency_key="idemp_same_key",
        create_payment_fn=mock_create_payment,
    )
    assert hold1.id == hold2.id
    assert pay1.id == pay2.id


def test_missing_dependency_raises_blocker(db_conn):
    # When create_payment_fn is not provided and genuine module not installed, raises DependencyBlockerError
    with pytest.raises(DependencyBlockerError) as exc:
        create_hold(
            db_conn,
            user_id=1,
            event_id=1,
            qty=2,
            idempotency_key="idemp_no_dep",
        )
    assert exc.value.code == "DEPENDENCY_BLOCKER"
    assert exc.value.http_status == 503


def test_fulfill_ticket_hold_multi_seat_and_idempotency(db_conn):
    hold, payment = create_hold(
        db_conn,
        user_id=1,
        event_id=1,
        qty=2,
        idempotency_key="idemp_to_fulfill",
        create_payment_fn=mock_create_payment,
    )

    # First fulfillment: succeeds and generates exactly 2 tickets with seat_index 1 and 2
    res1 = fulfill_ticket_hold(db_conn, payment, manual=False, now="2026-10-10T10:05:00Z")
    assert res1.outcome == "FULFILLED"

    tickets = db_conn.execute("SELECT * FROM tickets WHERE hold_id = ? ORDER BY seat_index ASC;", (hold.id,)).fetchall()
    assert len(tickets) == 2
    assert tickets[0]["seat_index"] == 1
    assert tickets[1]["seat_index"] == 2
    assert tickets[0]["code"] != tickets[1]["code"]

    # Second fulfillment: idempotent replay
    res2 = fulfill_ticket_hold(db_conn, payment, manual=False, now="2026-10-10T10:06:00Z")
    assert res2.outcome == "FULFILLED"

    # Ticket count remains 2
    count = db_conn.execute("SELECT COUNT(*) AS c FROM tickets WHERE hold_id = ?;", (hold.id,)).fetchone()["c"]
    assert count == 2


def test_ticket_checkin_lifecycle(db_conn):
    hold, payment = create_hold(
        db_conn,
        user_id=1,
        event_id=1,
        qty=1,
        idempotency_key="idemp_chk",
        create_payment_fn=mock_create_payment,
    )
    fulfill_ticket_hold(db_conn, payment, manual=False, now="2026-10-10T10:05:00Z")

    ticket = db_conn.execute("SELECT * FROM tickets WHERE hold_id = ?;", (hold.id,)).fetchone()
    code = ticket["code"]

    # First check-in: succeeds
    res1 = check_in(db_conn, event_id=1, code=code, staff_id=3)
    assert res1.status == "OK"
    assert res1.ticket_id == ticket["id"]

    # Verify status in database
    t_after = db_conn.execute("SELECT status, used_at, used_by FROM tickets WHERE id = ?;", (ticket["id"],)).fetchone()
    assert t_after["status"] == "USED"
    assert t_after["used_at"] is not None
    assert t_after["used_by"] == 3

    # Second check-in: ALREADY_USED
    res2 = check_in(db_conn, event_id=1, code=code, staff_id=3)
    assert res2.status == "ALREADY_USED"
    assert "already used" in res2.message.lower()

    # Wrong event check-in: REJECTED
    res_wrong_event = check_in(db_conn, event_id=2, code=code, staff_id=3)
    assert res_wrong_event.status == "REJECTED"
    assert "another event" in res_wrong_event.message.lower()

    # Unknown code check-in: REJECTED
    res_unknown = check_in(db_conn, event_id=1, code="UNKNOWN-CODE", staff_id=3)
    assert res_unknown.status == "REJECTED"


def test_expire_holds_frees_capacity(db_conn):
    # Reserve 2 seats under hold
    hold, pay = create_hold(
        db_conn,
        user_id=1,
        event_id=1,
        qty=2,
        idempotency_key="idemp_exp",
        create_payment_fn=mock_create_payment,
    )
    avail_before = get_available_seats(db_conn, 1, 10, "2026-10-10T10:00:00Z")
    assert avail_before == 8

    # Fast forward clock past hold TTL (10 min -> 600s)
    expired_count = expire_holds(db_conn, as_of="2026-10-10T10:15:00Z")
    assert expired_count == 1

    # Capacity is freed
    avail_after = get_available_seats(db_conn, 1, 10, "2026-10-10T10:15:00Z")
    assert avail_after == 10

    # Rerunning expire_holds does not double free
    rerun = expire_holds(db_conn, as_of="2026-10-10T10:15:00Z")
    assert rerun == 0


def test_event_report_and_cancellation(db_conn):
    # Alice books 2 tickets for event 1
    hold, payment = create_hold(
        db_conn,
        user_id=1,
        event_id=1,
        qty=2,
        idempotency_key="idemp_rep",
        create_payment_fn=mock_create_payment,
    )
    fulfill_ticket_hold(db_conn, payment, manual=False, now="2026-10-10T10:05:00Z")

    # Bob books free ticket for event 2
    hold_free, _ = create_hold(db_conn, user_id=2, event_id=2, qty=1, idempotency_key="idemp_free_rep")

    # Check in Alice's first ticket
    ticket1 = db_conn.execute("SELECT code FROM tickets WHERE hold_id = ? AND seat_index = 1;", (hold.id,)).fetchone()
    check_in(db_conn, event_id=1, code=ticket1["code"], staff_id=3)

    # Initial report for Event 1: sold=2, attended=1, no_shows=1, gross=160000 paise
    rep1 = event_report(db_conn, 1)
    assert rep1.sold == 2
    assert rep1.attended == 1
    assert rep1.no_shows == 1
    assert rep1.gross == 160000
    assert rep1.refunded == 0
    assert rep1.net_proceeds == 160000

    # Cancel Event 2 (free tickets become VOID)
    cancel_res2 = cancel_event(db_conn, None, event_id=2, actor_id=3)
    assert cancel_res2.void_count == 1
    t2 = db_conn.execute("SELECT status FROM tickets WHERE hold_id = ?;", (hold_free.id,)).fetchone()
    assert t2["status"] == "VOID"


def test_seed_events_creates_default(db_conn):
    db_conn.execute("DELETE FROM events;")
    seed_events(db_conn)
    row = db_conn.execute("SELECT title, capacity FROM events WHERE id = 1;").fetchone()
    assert row["title"] == "Spring Gala 2027"
    assert row["capacity"] == 100
