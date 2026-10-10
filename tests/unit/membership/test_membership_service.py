import sqlite3
import pytest

from clubledger.core import clock
from clubledger.core.db import apply_migrations, connect
from clubledger.core.errors import DomainError
from clubledger.core.types import FulfillResult, Payment
from clubledger.membership.service import (
    DUES_PURPOSE_HANDLER,
    DependencyBlockerError,
    apply_refund_dues,
    check_refundable_dues,
    enqueue_renewal_reminders,
    fulfill_dues,
    lookup_member,
    seed_plans,
    start_join,
)
import clubledger.membership.service as membership_service


def mock_create_payment(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    purpose: str,
    ref_table: str,
    ref_id: int,
    amount_paise: int,
) -> Payment:
    # Get or insert an OPEN term
    term_row = conn.execute("SELECT id FROM terms WHERE status = 'OPEN' LIMIT 1;").fetchone()
    term_id = term_row["id"] if term_row else 1
    cur = conn.execute(
        "INSERT INTO payments (public_id, user_id, purpose, ref_table, ref_id, amount_paise, currency, status, fulfillment, term_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'INR', 'CREATED', 'NONE', ?, ?);",
        (f"pay_{ref_id}", user_id, purpose, ref_table, ref_id, amount_paise, term_id, clock.now()),
    )
    return Payment(
        id=cur.lastrowid,  # type: ignore
        public_id=f"pay_{ref_id}",
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
    # Seed base term and user
    conn.execute(
        "INSERT INTO terms (id, label, starts_at, ends_at, status, closed_at, created_at) "
        "VALUES (1, 'Term 2026-27', '2026-08-01T00:00:00Z', NULL, 'OPEN', NULL, ?);",
        (clock.now(),),
    )
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (1, 'member@test.com', 'Saksham Singh', 'scrypt_hash', 1, ?);",
        (clock.now(),),
    )
    seed_plans(conn)
    yield conn
    conn.close()
    clock.reset()


def test_start_join_and_fulfill_dues_lifecycle(db_conn):
    payment = start_join(
        db_conn,
        user_id=1,
        plan_id=1,
        idempotency_key="idemp_join_1",
        create_payment_fn=mock_create_payment,
    )
    assert payment.user_id == 1
    assert payment.amount_paise == 200000
    assert payment.purpose == "DUES"

    # Verify membership created in PENDING status
    m_row = db_conn.execute("SELECT * FROM memberships WHERE id = ?;", (payment.ref_id,)).fetchone()
    assert m_row["status"] == "PENDING"
    assert m_row["member_code"] is None
    assert m_row["qr_token"] is None

    # Idempotent replay of start_join returns same payment
    replayed = start_join(
        db_conn,
        user_id=1,
        plan_id=1,
        idempotency_key="idemp_join_1",
        create_payment_fn=mock_create_payment,
    )
    assert replayed.id == payment.id

    # Fulfill dues
    res = fulfill_dues(db_conn, payment, manual=False, now=clock.now())
    assert res.outcome == "FULFILLED"

    # Verify membership now ACTIVE with code and qr_token
    active_m = db_conn.execute("SELECT * FROM memberships WHERE id = ?;", (payment.ref_id,)).fetchone()
    assert active_m["status"] == "ACTIVE"
    assert active_m["member_code"] is not None
    assert active_m["qr_token"] is not None

    # Replay fulfillment is idempotent
    res_again = fulfill_dues(db_conn, payment, manual=False, now=clock.now())
    assert res_again.outcome == "FULFILLED"


def test_duplicate_membership_in_same_academic_year_blocked(db_conn):
    start_join(
        db_conn,
        user_id=1,
        plan_id=1,
        idempotency_key="join_key_1",
        create_payment_fn=mock_create_payment,
    )

    # Second attempt with distinct idempotency key in same year raises ALREADY_MEMBER
    with pytest.raises(DomainError) as exc_info:
        start_join(
            db_conn,
            user_id=1,
            plan_id=1,
            idempotency_key="join_key_2",
            create_payment_fn=mock_create_payment,
        )
    assert exc_info.value.code == "ALREADY_MEMBER"
    assert exc_info.value.http_status == 409


def test_future_renewal_within_30_days_of_expiry(db_conn):
    # Member with active membership expiring 2027-07-31T18:30:00Z
    clock.set_now("2026-10-10T10:00:00Z")
    pay = start_join(
        db_conn,
        user_id=1,
        plan_id=1,
        idempotency_key="join_curr",
        create_payment_fn=mock_create_payment,
    )
    fulfill_dues(db_conn, pay, manual=False, now=clock.now())

    # Advance clock to within 30 days of expiry: e.g. 2027-07-15T10:00:00Z
    clock.set_now("2027-07-15T10:00:00Z")
    renewal_pay = start_join(
        db_conn,
        user_id=1,
        plan_id=1,
        idempotency_key="renewal_next",
        create_payment_fn=mock_create_payment,
    )
    assert renewal_pay.id != pay.id

    # Verify renewal created for next year
    renew_m = db_conn.execute("SELECT * FROM memberships WHERE id = ?;", (renewal_pay.ref_id,)).fetchone()
    assert renew_m["membership_year"] == "2027-28"
    assert renew_m["status"] == "PENDING"
    assert renew_m["starts_at"] == "2027-07-31T18:30:00Z"


def test_lookup_member_active_and_expired(db_conn):
    pay = start_join(
        db_conn,
        user_id=1,
        plan_id=1,
        idempotency_key="lookup_join",
        create_payment_fn=mock_create_payment,
    )
    fulfill_dues(db_conn, pay, manual=False, now=clock.now())
    m = db_conn.execute("SELECT member_code, qr_token FROM memberships WHERE id = ?;", (pay.ref_id,)).fetchone()

    # Lookup by code when active
    check = lookup_member(db_conn, code=m["member_code"], at=clock.now())
    assert check.active is True
    assert check.name == "Saksham Singh"
    assert check.status == "ACTIVE"

    # Lookup by qr_token when active
    check_qr = lookup_member(db_conn, qr_token=m["qr_token"], at=clock.now())
    assert check_qr.active is True

    # Advance time past expiration
    check_future = lookup_member(db_conn, code=m["member_code"], at="2027-08-05T00:00:00Z")
    assert check_future.active is False
    assert check_future.status == "EXPIRED"

    # Unknown code returns NOT_FOUND
    check_unknown = lookup_member(db_conn, code="M9999-NONEXIST", at=clock.now())
    assert check_unknown.active is False
    assert check_unknown.status == "NOT_FOUND"


def test_dues_purpose_handler_wiring_and_refund(db_conn):
    assert DUES_PURPOSE_HANDLER.purpose == "DUES"
    pay = start_join(
        db_conn,
        user_id=1,
        plan_id=1,
        idempotency_key="handler_join",
        create_payment_fn=mock_create_payment,
    )
    DUES_PURPOSE_HANDLER.fulfill(db_conn, pay, manual=False, now=clock.now())

    # Refund check passes
    DUES_PURPOSE_HANDLER.check_refundable(db_conn, pay)

    # Apply refund transitions to REVOKED
    DUES_PURPOSE_HANDLER.apply_refund(db_conn, pay, clock.now())
    m = db_conn.execute("SELECT status FROM memberships WHERE id = ?;", (pay.ref_id,)).fetchone()
    assert m["status"] == "REVOKED"

    # Subsequent refund check fails with REFUND_BLOCKED
    with pytest.raises(DomainError) as exc:
        DUES_PURPOSE_HANDLER.check_refundable(db_conn, pay)
    assert exc.value.code == "REFUND_BLOCKED"


def test_missing_payment_service_raises_dependency_blocker(db_conn, monkeypatch):
    # Explicitly simulate absence in isolated unit test per TURBO_B.txt
    monkeypatch.setattr(membership_service, "_genuine_create_payment", None)
    with pytest.raises(DependencyBlockerError):
        start_join(
            db_conn,
            user_id=1,
            plan_id=1,
            idempotency_key="blocker_key",
            create_payment_fn=None,
        )


def test_start_join_with_genuine_payment_service(db_conn):
    # Verify real dependency behavior now that A's payments module is integrated
    payment = start_join(
        db_conn,
        user_id=1,
        plan_id=1,
        idempotency_key="genuine_dep_join_key",
    )
    assert payment.id is not None
    assert payment.purpose == "DUES"
    assert payment.ref_table == "memberships"


def test_start_join_idempotency_different_parameters_conflict(db_conn):
    start_join(db_conn, user_id=1, plan_id=1, idempotency_key="same_join_key")
    with pytest.raises(DomainError) as exc:
        # Changed plan_id with same actor/action/key
        start_join(db_conn, user_id=1, plan_id=2, idempotency_key="same_join_key")
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"
    assert exc.value.http_status == 422
