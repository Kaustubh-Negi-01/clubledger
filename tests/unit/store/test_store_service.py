"""Unit tests for store and merchandise service per CONTRACT.md §1.5, §8, §13.3, STO-01 to STO-09."""

import sqlite3
import pytest

from clubledger.core import clock
from clubledger.core.db import apply_migrations, connect
from clubledger.core.errors import DomainError
from clubledger.core.types import CartItem, FulfillResult, Payment
from clubledger.store.service import (
    MERCH_PURPOSE_HANDLER,
    DependencyBlockerError,
    apply_refund_merch,
    cancel_order,
    check_refundable_merch,
    expire_orders,
    fulfill_merch_order,
    mark_picked_up,
    reserve_cart,
    seed_store,
)
import clubledger.store.service as store_service


def mock_create_payment(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    purpose: str,
    ref_table: str,
    ref_id: int,
    amount_paise: int,
) -> Payment:
    """Mock payment creation for testing paid cart reservations."""
    term_row = conn.execute("SELECT id FROM terms WHERE status = 'OPEN' LIMIT 1;").fetchone()
    term_id = term_row["id"] if term_row else 1
    cur = conn.execute(
        "INSERT INTO payments (public_id, user_id, purpose, ref_table, ref_id, amount_paise, currency, status, fulfillment, term_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'INR', 'CREATED', 'NONE', ?, ?);",
        (f"pay_order_{ref_id}", user_id, purpose, ref_table, ref_id, amount_paise, term_id, clock.now()),
    )
    return Payment(
        id=cur.lastrowid,  # type: ignore
        public_id=f"pay_order_{ref_id}",
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

    # Seed membership plan and active membership for Alice (10% discount = 1000 bps)
    conn.execute(
        "INSERT INTO membership_plans (id, code, name, dues_paise, ticket_discount_bps, merch_discount_bps, is_active, created_at) "
        "VALUES (1, 'annual_std', 'Standard Plan', 50000, 2000, 1000, 1, '2026-10-10T00:00:00Z');"
    )
    conn.execute(
        "INSERT INTO memberships (id, user_id, plan_id, membership_year, status, starts_at, expires_at, member_code, qr_token, created_at) "
        "VALUES (1, 1, 1, '2026-27', 'ACTIVE', '2026-08-01T00:00:00Z', '2027-07-31T23:59:59Z', 'MEM-ALICE', 'QR-ALICE', '2026-10-10T00:00:00Z');"
    )

    # Seed standard store products
    seed_store(conn)

    yield conn
    conn.close()
    clock.reset()


def test_seed_store_creates_default_hoodie(db_conn):
    products = db_conn.execute("SELECT * FROM products;").fetchall()
    assert len(products) == 1
    assert products[0]["name"] == "Club Classic Hoodie"
    assert products[0]["base_price_paise"] == 250000

    variants = db_conn.execute("SELECT * FROM variants WHERE product_id = ? ORDER BY id ASC;", (products[0]["id"],)).fetchall()
    assert len(variants) == 4
    sizes = [v["size"] for v in variants]
    assert sizes == ["S", "M", "L", "XL"]
    stocks = [v["physical_qty"] for v in variants]
    assert stocks == [10, 25, 20, 10]
    for v in variants:
        assert v["reserved_qty"] == 0


def test_reserve_cart_member_vs_public_pricing(db_conn):
    # Public user Bob buys Hoodie M (base 250000 paise = ₹2500.00)
    items = [CartItem(variant_id=2, qty=1)]
    order_bob, pay_bob = reserve_cart(
        db_conn,
        user_id=2,
        items=items,
        idempotency_key="idemp_store_bob",
        create_payment_fn=mock_create_payment,
    )
    assert order_bob.price_tier == "PUBLIC"
    assert order_bob.total_paise == 250000
    assert pay_bob.amount_paise == 250000

    # Member user Alice buys Hoodie M with 10% discount (250000 * 9000 // 10000 = 225000 paise = ₹2250.00)
    order_alice, pay_alice = reserve_cart(
        db_conn,
        user_id=1,
        items=items,
        idempotency_key="idemp_store_alice",
        create_payment_fn=mock_create_payment,
    )
    assert order_alice.price_tier == "MEMBER"
    assert order_alice.total_paise == 225000
    assert pay_alice.amount_paise == 225000


def test_reserve_cart_atomic_stock_reservation(db_conn):
    v_before = db_conn.execute("SELECT physical_qty, reserved_qty FROM variants WHERE id = 1;").fetchone()
    assert v_before["physical_qty"] == 10
    assert v_before["reserved_qty"] == 0

    items = [CartItem(variant_id=1, qty=3)]
    order, payment = reserve_cart(
        db_conn,
        user_id=1,
        items=items,
        idempotency_key="idemp_stock_atomic",
        create_payment_fn=mock_create_payment,
    )
    assert order.status == "RESERVED"

    v_after = db_conn.execute("SELECT physical_qty, reserved_qty FROM variants WHERE id = 1;").fetchone()
    # Physical stock unchanged, reserved_qty increments by 3
    assert v_after["physical_qty"] == 10
    assert v_after["reserved_qty"] == 3

    # Available stock is physical - reserved = 7
    available = v_after["physical_qty"] - v_after["reserved_qty"]
    assert available == 7


def test_competing_last_stock_purchases(db_conn):
    # Set variant 1 to physical_qty=1, reserved_qty=0 (exactly 1 unit left)
    db_conn.execute("UPDATE variants SET physical_qty = 1, reserved_qty = 0 WHERE id = 1;")

    items = [CartItem(variant_id=1, qty=1)]
    # First customer reserves the last unit
    order1, pay1 = reserve_cart(
        db_conn,
        user_id=1,
        items=items,
        idempotency_key="idemp_competing_1",
        create_payment_fn=mock_create_payment,
    )
    assert order1.status == "RESERVED"

    # Second competing customer requests the last unit -> rejected with 409 INSUFFICIENT_STOCK
    with pytest.raises(DomainError) as exc_info:
        reserve_cart(
            db_conn,
            user_id=2,
            items=items,
            idempotency_key="idemp_competing_2",
            create_payment_fn=mock_create_payment,
        )
    assert exc_info.value.http_status == 409
    assert exc_info.value.code == "INSUFFICIENT_STOCK"

    # Stock invariant maintained
    v = db_conn.execute("SELECT physical_qty, reserved_qty FROM variants WHERE id = 1;").fetchone()
    assert v["physical_qty"] == 1
    assert v["reserved_qty"] == 1


def test_quantity_limits_and_duplicate_variants(db_conn):
    # Empty cart
    with pytest.raises(DomainError) as exc:
        reserve_cart(db_conn, user_id=1, items=[], idempotency_key="idemp_empty", create_payment_fn=mock_create_payment)
    assert exc.value.http_status == 422
    assert exc.value.code == "VALIDATION"

    # Zero quantity
    with pytest.raises(DomainError) as exc:
        reserve_cart(
            db_conn,
            user_id=1,
            items=[CartItem(variant_id=1, qty=0)],
            idempotency_key="idemp_zero",
            create_payment_fn=mock_create_payment,
        )
    assert exc.value.http_status == 422

    # Negative quantity
    with pytest.raises(DomainError) as exc:
        reserve_cart(
            db_conn,
            user_id=1,
            items=[CartItem(variant_id=1, qty=-2)],
            idempotency_key="idemp_neg",
            create_payment_fn=mock_create_payment,
        )
    assert exc.value.http_status == 422

    # Greater than max quantity (11 > 10)
    with pytest.raises(DomainError) as exc:
        reserve_cart(
            db_conn,
            user_id=1,
            items=[CartItem(variant_id=1, qty=11)],
            idempotency_key="idemp_11",
            create_payment_fn=mock_create_payment,
        )
    assert exc.value.http_status == 422

    # Duplicate variant in same cart
    with pytest.raises(DomainError) as exc:
        reserve_cart(
            db_conn,
            user_id=1,
            items=[CartItem(variant_id=1, qty=2), CartItem(variant_id=1, qty=3)],
            idempotency_key="idemp_dup",
            create_payment_fn=mock_create_payment,
        )
    assert exc.value.http_status == 422
    assert "Duplicate" in exc.value.message


def test_reserve_cart_idempotency_replay_and_conflict(db_conn):
    items1 = [CartItem(variant_id=1, qty=2)]
    order1, pay1 = reserve_cart(
        db_conn,
        user_id=1,
        items=items1,
        idempotency_key="idemp_key_store",
        create_payment_fn=mock_create_payment,
    )

    # Identical request with same key -> returns original order & payment
    order_replay, pay_replay = reserve_cart(
        db_conn,
        user_id=1,
        items=items1,
        idempotency_key="idemp_key_store",
        create_payment_fn=mock_create_payment,
    )
    assert order_replay.id == order1.id
    assert pay_replay.id == pay1.id

    # Changed parameters with same key -> 409 CONFLICT
    items2 = [CartItem(variant_id=1, qty=4)]
    with pytest.raises(DomainError) as exc_info:
        reserve_cart(
            db_conn,
            user_id=1,
            items=items2,
            idempotency_key="idemp_key_store",
            create_payment_fn=mock_create_payment,
        )
    assert exc_info.value.http_status == 422
    assert exc_info.value.code == "IDEMPOTENCY_CONFLICT"


def test_reserve_cart_missing_payment_dependency_raises_blocker(db_conn, monkeypatch):
    monkeypatch.setattr(store_service, "_genuine_create_payment", None)
    with pytest.raises(DependencyBlockerError) as exc_info:
        reserve_cart(
            db_conn,
            user_id=1,
            items=[CartItem(variant_id=1, qty=1)],
            idempotency_key="idemp_missing_pay",
            create_payment_fn=None,
        )
    assert exc_info.value.http_status == 503
    assert exc_info.value.code == "DEPENDENCY_BLOCKER"


def test_fulfill_merch_order_lifecycle(db_conn):
    items = [CartItem(variant_id=1, qty=2)]
    order, payment = reserve_cart(
        db_conn,
        user_id=1,
        items=items,
        idempotency_key="idemp_fulfill_life",
        create_payment_fn=mock_create_payment,
    )
    assert order.status == "RESERVED"

    # Fulfillment succeeds
    res = fulfill_merch_order(db_conn, payment, manual=False, now="2026-10-10T10:05:00Z")
    assert res.outcome == "FULFILLED"

    o_row = db_conn.execute("SELECT status FROM merch_orders WHERE id = ?;", (order.id,)).fetchone()
    assert o_row["status"] == "PAID"

    # Reserved stock remains reserved until staff pickup
    v = db_conn.execute("SELECT physical_qty, reserved_qty FROM variants WHERE id = 1;").fetchone()
    assert v["physical_qty"] == 10
    assert v["reserved_qty"] == 2

    # Idempotent replay: second fulfillment call returns FULFILLED without change
    res2 = fulfill_merch_order(db_conn, payment, manual=False, now="2026-10-10T10:06:00Z")
    assert res2.outcome == "FULFILLED"


def test_delayed_callback_on_expired_order_releases_stock(db_conn):
    # Reserve cart at 10:00:00Z (TTL = 10 min -> expires 10:10:00Z)
    clock.set_now("2026-10-10T10:00:00Z")
    items = [CartItem(variant_id=1, qty=2)]
    order, payment = reserve_cart(
        db_conn,
        user_id=1,
        items=items,
        idempotency_key="idemp_delayed_cb",
        create_payment_fn=mock_create_payment,
    )
    assert order.status == "RESERVED"

    v1 = db_conn.execute("SELECT reserved_qty FROM variants WHERE id = 1;").fetchone()
    assert v1["reserved_qty"] == 2

    # Delayed callback arrives at 10:15:00Z (after expiry)
    res = fulfill_merch_order(db_conn, payment, manual=False, now="2026-10-10T10:15:00Z")
    assert res.outcome == "UNFULFILLABLE"
    assert res.reason == "TARGET_NOT_LIVE"

    # Order marked EXPIRED and reserved stock released
    o_row = db_conn.execute("SELECT status FROM merch_orders WHERE id = ?;", (order.id,)).fetchone()
    assert o_row["status"] == "EXPIRED"

    v2 = db_conn.execute("SELECT reserved_qty FROM variants WHERE id = 1;").fetchone()
    assert v2["reserved_qty"] == 0


def test_manual_fulfillment_of_expired_order(db_conn):
    # Reserve cart at 10:00:00Z
    clock.set_now("2026-10-10T10:00:00Z")
    items = [CartItem(variant_id=1, qty=2)]
    order, payment = reserve_cart(
        db_conn,
        user_id=1,
        items=items,
        idempotency_key="idemp_manual_exp",
        create_payment_fn=mock_create_payment,
    )
    # Expire order via background sweep
    expire_orders(db_conn, as_of="2026-10-10T10:12:00Z")
    o_row = db_conn.execute("SELECT status FROM merch_orders WHERE id = ?;", (order.id,)).fetchone()
    assert o_row["status"] == "EXPIRED"

    # Staff manual fulfillment checks live stock, re-reserves, and marks PAID
    res = fulfill_merch_order(db_conn, payment, manual=True, now="2026-10-10T10:15:00Z")
    assert res.outcome == "FULFILLED"

    o_row2 = db_conn.execute("SELECT status FROM merch_orders WHERE id = ?;", (order.id,)).fetchone()
    assert o_row2["status"] == "PAID"

    v = db_conn.execute("SELECT reserved_qty FROM variants WHERE id = 1;").fetchone()
    assert v["reserved_qty"] == 2


def test_expire_orders_releases_reserved_stock_once(db_conn):
    clock.set_now("2026-10-10T10:00:00Z")
    items = [CartItem(variant_id=1, qty=3)]
    order, payment = reserve_cart(
        db_conn,
        user_id=1,
        items=items,
        idempotency_key="idemp_sweep",
        create_payment_fn=mock_create_payment,
    )
    v1 = db_conn.execute("SELECT reserved_qty FROM variants WHERE id = 1;").fetchone()
    assert v1["reserved_qty"] == 3

    # Run sweep before TTL -> 0 expired
    count0 = expire_orders(db_conn, as_of="2026-10-10T10:05:00Z")
    assert count0 == 0

    # Run sweep after TTL -> 1 expired
    count1 = expire_orders(db_conn, as_of="2026-10-10T10:11:00Z")
    assert count1 == 1

    v2 = db_conn.execute("SELECT reserved_qty FROM variants WHERE id = 1;").fetchone()
    assert v2["reserved_qty"] == 0

    # Repeat sweep does not decrement stock again
    count2 = expire_orders(db_conn, as_of="2026-10-10T10:20:00Z")
    assert count2 == 0
    v3 = db_conn.execute("SELECT reserved_qty FROM variants WHERE id = 1;").fetchone()
    assert v3["reserved_qty"] == 0


def test_mark_picked_up_decrements_both_physical_and_reserved(db_conn):
    items = [CartItem(variant_id=1, qty=4)]
    order, payment = reserve_cart(
        db_conn,
        user_id=1,
        items=items,
        idempotency_key="idemp_pickup",
        create_payment_fn=mock_create_payment,
    )
    fulfill_merch_order(db_conn, payment, manual=False, now="2026-10-10T10:05:00Z")

    v_before = db_conn.execute("SELECT physical_qty, reserved_qty FROM variants WHERE id = 1;").fetchone()
    assert v_before["physical_qty"] == 10
    assert v_before["reserved_qty"] == 4

    # Staff performs pickup
    mark_picked_up(db_conn, order_id=order.id, staff_id=3)

    o_row = db_conn.execute("SELECT status, picked_up_by, picked_up_at FROM merch_orders WHERE id = ?;", (order.id,)).fetchone()
    assert o_row["status"] == "PICKED_UP"
    assert o_row["picked_up_by"] == 3
    assert o_row["picked_up_at"] is not None

    # Both physical_qty and reserved_qty fall by qty
    v_after = db_conn.execute("SELECT physical_qty, reserved_qty FROM variants WHERE id = 1;").fetchone()
    assert v_after["physical_qty"] == 6
    assert v_after["reserved_qty"] == 0


def test_mark_picked_up_twice_and_invalid_status_conflict(db_conn):
    items = [CartItem(variant_id=1, qty=1)]
    order, payment = reserve_cart(
        db_conn,
        user_id=1,
        items=items,
        idempotency_key="idemp_pickup_twice",
        create_payment_fn=mock_create_payment,
    )

    # Pickup before payment (order is RESERVED) -> 409 CONFLICT
    with pytest.raises(DomainError) as exc1:
        mark_picked_up(db_conn, order_id=order.id, staff_id=3)
    assert exc1.value.http_status == 409
    assert exc1.value.code == "CONFLICT"

    # Fulfill payment
    fulfill_merch_order(db_conn, payment, manual=False, now="2026-10-10T10:05:00Z")

    # First pickup succeeds
    mark_picked_up(db_conn, order_id=order.id, staff_id=3)

    # Second pickup call -> 409 CONFLICT
    with pytest.raises(DomainError) as exc2:
        mark_picked_up(db_conn, order_id=order.id, staff_id=3)
    assert exc2.value.http_status == 409
    assert exc2.value.code == "CONFLICT"


def test_refund_before_pickup_releases_reserved_stock(db_conn):
    items = [CartItem(variant_id=1, qty=2)]
    order, payment = reserve_cart(
        db_conn,
        user_id=1,
        items=items,
        idempotency_key="idemp_refund_ok",
        create_payment_fn=mock_create_payment,
    )
    fulfill_merch_order(db_conn, payment, manual=False, now="2026-10-10T10:05:00Z")

    # Check refundable passes
    check_refundable_merch(db_conn, payment)

    # Apply refund
    apply_refund_merch(db_conn, payment, now="2026-10-10T10:08:00Z")

    o_row = db_conn.execute("SELECT status FROM merch_orders WHERE id = ?;", (order.id,)).fetchone()
    assert o_row["status"] == "REFUNDED"

    # Reserved stock released, physical stock untouched
    v = db_conn.execute("SELECT physical_qty, reserved_qty FROM variants WHERE id = 1;").fetchone()
    assert v["physical_qty"] == 10
    assert v["reserved_qty"] == 0


def test_refund_after_pickup_blocked(db_conn):
    items = [CartItem(variant_id=1, qty=1)]
    order, payment = reserve_cart(
        db_conn,
        user_id=1,
        items=items,
        idempotency_key="idemp_refund_blocked",
        create_payment_fn=mock_create_payment,
    )
    fulfill_merch_order(db_conn, payment, manual=False, now="2026-10-10T10:05:00Z")
    mark_picked_up(db_conn, order_id=order.id, staff_id=3)

    # Check refundable on picked up order raises 409 REFUND_BLOCKED
    with pytest.raises(DomainError) as exc_info:
        check_refundable_merch(db_conn, payment)
    assert exc_info.value.http_status == 409
    assert exc_info.value.code == "REFUND_BLOCKED"
    assert "Cannot refund order after pickup" in exc_info.value.message


def test_cancel_order_unpaid_releases_reserved_stock(db_conn):
    items = [CartItem(variant_id=1, qty=3)]
    order, payment = reserve_cart(
        db_conn,
        user_id=1,
        items=items,
        idempotency_key="idemp_cancel_unpaid",
        create_payment_fn=mock_create_payment,
    )
    assert order.status == "RESERVED"

    # User cancels unpaid reservation
    cancel_order(db_conn, handlers=None, order_id=order.id, actor_id=1)

    o_row = db_conn.execute("SELECT status FROM merch_orders WHERE id = ?;", (order.id,)).fetchone()
    assert o_row["status"] == "CANCELLED"

    v = db_conn.execute("SELECT reserved_qty FROM variants WHERE id = 1;").fetchone()
    assert v["reserved_qty"] == 0

    # Idempotent second cancel
    cancel_order(db_conn, handlers=None, order_id=order.id, actor_id=1)
    assert v["reserved_qty"] == 0


def test_cancel_order_paid_calls_refund_payment(db_conn):
    from clubledger.payments.service import create_payment

    items = [CartItem(variant_id=1, qty=2)]
    order, payment = reserve_cart(
        db_conn,
        user_id=1,
        items=items,
        idempotency_key="idemp_cancel_paid",
        create_payment_fn=create_payment,
    )
    # Simulate payment success
    db_conn.execute("UPDATE payments SET status = 'SUCCEEDED' WHERE id = ?;", (payment.id,))
    fulfill_merch_order(db_conn, payment, manual=False, now=clock.now())

    # Cancel paid order via refund_payment
    handlers = {"MERCH": MERCH_PURPOSE_HANDLER}
    cancel_order(db_conn, handlers=handlers, order_id=order.id, actor_id=1)

    o_row = db_conn.execute("SELECT status FROM merch_orders WHERE id = ?;", (order.id,)).fetchone()
    assert o_row["status"] == "REFUNDED"

    p_row = db_conn.execute("SELECT status FROM payments WHERE id = ?;", (payment.id,)).fetchone()
    assert p_row["status"] == "REFUNDED"

    v = db_conn.execute("SELECT reserved_qty FROM variants WHERE id = 1;").fetchone()
    assert v["reserved_qty"] == 0
