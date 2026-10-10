"""Store and merchandise service per CONTRACT.md §1.5, §13.3, §8, STO-01 to STO-09."""

from datetime import datetime, timedelta, timezone
import hashlib
import sqlite3
from typing import Any, Callable, Literal

from clubledger.core import clock
from clubledger.core.errors import DomainError
from clubledger.core.types import (
    CartItem,
    FulfillResult,
    MerchOrder,
    Payment,
    PurposeHandler,
)

# Attempt to import genuine A-owned pricing and payments
try:
    from clubledger.core.pricing import merch_price as _genuine_merch_price
except ImportError:
    _genuine_merch_price = None

try:
    from clubledger.payments.service import create_payment as _genuine_create_payment
except ImportError:
    _genuine_create_payment = None


class DependencyBlockerError(DomainError):
    """Raised when an A-owned or D-owned dependency is not yet implemented."""

    def __init__(self, message: str) -> None:
        super().__init__("DEPENDENCY_BLOCKER", 503, message)


def seed_store(conn: sqlite3.Connection) -> None:
    """Seed demo merchandise products and variants per CONTRACT defaults."""
    exists = conn.execute("SELECT 1 FROM products LIMIT 1;").fetchone()
    if not exists:
        now_str = clock.now()
        # Seed Hoodie
        cur = conn.execute(
            "INSERT INTO products (id, name, description, base_price_paise, is_active, created_at) "
            "VALUES (1, 'Club Classic Hoodie', 'Official skyline cotton fleece hoodie', 250000, 1, ?);",
            (now_str,),
        )
        product_id = cur.lastrowid
        assert product_id is not None
        # Seed variants (S, M, L, XL)
        variants = [
            ("HOODIE-S", "S", 10),
            ("HOODIE-M", "M", 25),
            ("HOODIE-L", "L", 20),
            ("HOODIE-XL", "XL", 10),
        ]
        for idx, (sku, size, stock) in enumerate(variants, start=1):
            conn.execute(
                "INSERT INTO variants (id, product_id, sku, size, physical_qty, reserved_qty, created_at) "
                "VALUES (?, ?, ?, ?, ?, 0, ?);",
                (idx, product_id, sku, size, stock, now_str),
            )


def _compute_merch_price_fallback(
    conn: sqlite3.Connection,
    base_paise: int,
    user_id: int,
    now_str: str,
) -> tuple[int, Literal["MEMBER", "PUBLIC"]]:
    """Fallback merchandise price calculation strictly adhering to CONTRACT §2 floor math."""
    mem = conn.execute(
        "SELECT m.id, p.merch_discount_bps "
        "FROM memberships m "
        "JOIN membership_plans p ON m.plan_id = p.id "
        "WHERE m.user_id = ? AND m.status = 'ACTIVE' "
        "  AND m.starts_at <= ? AND m.expires_at > ? "
        "ORDER BY m.id DESC LIMIT 1;",
        (user_id, now_str, now_str),
    ).fetchone()

    if mem:
        discount_bps = mem["merch_discount_bps"]
        discounted = base_paise * (10000 - discount_bps) // 10000
        # Prevent zero-price merchandise silently violating payment/item constraints
        final_price = max(1, discounted)
        return (final_price, "MEMBER")

    return (max(1, base_paise), "PUBLIC")


def reserve_cart(
    conn: sqlite3.Connection,
    user_id: int,
    items: list[CartItem],
    idempotency_key: str,
    *,
    pricing_fn: Callable[..., tuple[int, Literal["MEMBER", "PUBLIC"]]] | None = None,
    create_payment_fn: Callable[..., Payment] | None = None,
) -> tuple[MerchOrder, Payment]:
    """Atomically reserve a cart of merchandise items per CONTRACT §1.5, §13.3, STO-02."""
    now_str = clock.now()

    # 1. Validate user exists and is active
    user_row = conn.execute("SELECT id, is_active FROM users WHERE id = ?;", (user_id,)).fetchone()
    if not user_row or not user_row["is_active"]:
        raise DomainError("NOT_FOUND", 404, "Active user not found")

    # 2. Check canonical request hash for idempotency replay
    canonical_items = sorted([(it.variant_id, it.qty) for it in items])
    req_hash = hashlib.sha256(f"cart={canonical_items}".encode("utf-8")).hexdigest()

    existing_key = conn.execute(
        "SELECT request_hash, result_ref FROM idempotency_keys WHERE actor_user_id = ? AND action = 'store.reserve' AND key = ?;",
        (user_id, idempotency_key),
    ).fetchone()
    if existing_key:
        if existing_key["request_hash"] != req_hash:
            raise DomainError("CONFLICT", 409, "Idempotency key reused with different request parameters")

        ref = existing_key["result_ref"]
        # Format: order:{order_id}:pay:{payment_id}
        parts = ref.split(":")
        order_id = int(parts[1])
        pay_id = int(parts[3])

        o_row = conn.execute("SELECT * FROM merch_orders WHERE id = ?;", (order_id,)).fetchone()
        p_row = conn.execute("SELECT * FROM payments WHERE id = ?;", (pay_id,)).fetchone()

        if not o_row or not p_row:
            raise DomainError("NOT_FOUND", 404, "Existing order or payment record not found")

        order_obj = MerchOrder(
            id=o_row["id"],
            user_id=o_row["user_id"],
            status=o_row["status"],
            expires_at=o_row["expires_at"],
            total_paise=o_row["total_paise"],
            price_tier=o_row["price_tier"],
            payment_id=o_row["payment_id"],
            created_at=o_row["created_at"],
        )
        payment_obj = Payment(
            id=p_row["id"],
            public_id=p_row["public_id"],
            user_id=p_row["user_id"],
            purpose=p_row["purpose"],
            ref_table=p_row["ref_table"],
            ref_id=p_row["ref_id"],
            amount_paise=p_row["amount_paise"],
            status=p_row["status"],
            fulfillment=p_row["fulfillment"],
            term_id=p_row["term_id"],
        )
        return (order_obj, payment_obj)

    # 3. Validate cart items (STO-03)
    if not items:
        raise DomainError("VALIDATION", 422, "Cart cannot be empty")

    variant_ids = [it.variant_id for it in items]
    if len(variant_ids) != len(set(variant_ids)):
        raise DomainError("VALIDATION", 422, "Duplicate variant in cart")

    for it in items:
        if not isinstance(it.qty, int) or it.qty < 1 or it.qty > 10:
            raise DomainError("VALIDATION", 422, f"Item quantity must be an integer between 1 and 10, got {it.qty}")

    # 4. Validate variants and active products
    resolved_lines = []
    has_member_tier = False

    for it in items:
        var_row = conn.execute(
            "SELECT v.id, v.product_id, v.physical_qty, v.reserved_qty, "
            "       p.name AS product_name, p.base_price_paise, p.is_active AS product_active "
            "FROM variants v "
            "JOIN products p ON v.product_id = p.id "
            "WHERE v.id = ?;",
            (it.variant_id,),
        ).fetchone()

        if not var_row:
            raise DomainError("NOT_FOUND", 404, f"Variant {it.variant_id} not found")

        if not var_row["product_active"]:
            raise DomainError("VALIDATION", 422, f"Product {var_row['product_name']} is inactive")

        # Determine server-authoritative price per line
        pricer = pricing_fn or _genuine_merch_price
        if pricer is not None:
            unit_price, tier = pricer(conn, var_row["base_price_paise"], user_id, now_str)
        else:
            unit_price, tier = _compute_merch_price_fallback(conn, var_row["base_price_paise"], user_id, now_str)

        # Avoid zero-price merchandise silently violating payment/item constraints
        unit_price = max(1, unit_price)
        if tier == "MEMBER":
            has_member_tier = True

        resolved_lines.append(
            {
                "variant_id": it.variant_id,
                "qty": it.qty,
                "unit_price_paise": unit_price,
            }
        )

    order_tier: Literal["MEMBER", "PUBLIC"] = "MEMBER" if has_member_tier else "PUBLIC"
    total_paise = sum(line["unit_price_paise"] * line["qty"] for line in resolved_lines)

    # 5. Atomic stock reservation (STO-02, STO-08)
    for line in resolved_lines:
        updated = conn.execute(
            "UPDATE variants SET reserved_qty = reserved_qty + ? "
            "WHERE id = ? AND physical_qty - reserved_qty >= ?;",
            (line["qty"], line["variant_id"], line["qty"]),
        ).rowcount
        if updated != 1:
            raise DomainError("INSUFFICIENT_STOCK", 409, f"Insufficient stock for variant {line['variant_id']}")

    # 6. TTL = 10 minutes (600s)
    now_dt = datetime.fromisoformat(now_str.replace("Z", "+00:00")).astimezone(timezone.utc)
    expires_dt = now_dt + timedelta(seconds=600)
    expires_str = expires_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    cur = conn.execute(
        "INSERT INTO merch_orders ("
        "  user_id, status, expires_at, total_paise, price_tier, payment_id, "
        "  picked_up_at, picked_up_by, created_at"
        ") VALUES (?, 'RESERVED', ?, ?, ?, NULL, NULL, NULL, ?);",
        (user_id, expires_str, total_paise, order_tier, now_str),
    )
    order_id = cur.lastrowid
    assert order_id is not None

    # 7. Insert order items
    for line in resolved_lines:
        conn.execute(
            "INSERT INTO merch_order_items (order_id, variant_id, qty, unit_price_paise, created_at) "
            "VALUES (?, ?, ?, ?, ?);",
            (order_id, line["variant_id"], line["qty"], line["unit_price_paise"], now_str),
        )

    # 8. Create payment
    payment_creator = create_payment_fn or _genuine_create_payment
    if payment_creator is None:
        raise DependencyBlockerError(
            "payments.service.create_payment is not yet available; dependency blocker per BUILD_ORDER"
        )

    payment = payment_creator(
        conn,
        user_id=user_id,
        purpose="MERCH",
        ref_table="merch_orders",
        ref_id=order_id,
        amount_paise=total_paise,
    )

    conn.execute(
        "UPDATE merch_orders SET payment_id = ? WHERE id = ?;",
        (payment.id, order_id),
    )

    # 9. Record idempotency key
    conn.execute(
        "INSERT INTO idempotency_keys (actor_user_id, action, key, request_hash, result_ref, created_at) "
        "VALUES (?, 'store.reserve', ?, ?, ?, ?);",
        (user_id, idempotency_key, req_hash, f"order:{order_id}:pay:{payment.id}", now_str),
    )

    order_obj = MerchOrder(
        id=order_id,
        user_id=user_id,
        status="RESERVED",
        expires_at=expires_str,
        total_paise=total_paise,
        price_tier=order_tier,
        payment_id=payment.id,
        created_at=now_str,
    )
    return (order_obj, payment)


def fulfill_merch_order(
    conn: sqlite3.Connection,
    payment: Payment,
    *,
    manual: bool,
    now: str,
) -> FulfillResult:
    """Fulfill merchandise order transitioning RESERVED -> PAID per CONTRACT §1.5, STO-05."""
    order_row = conn.execute("SELECT * FROM merch_orders WHERE id = ?;", (payment.ref_id,)).fetchone()
    if not order_row:
        return FulfillResult(outcome="UNFULFILLABLE", reason="TARGET_NOT_LIVE")

    # Idempotent replay: already PAID or PICKED_UP
    if order_row["status"] in ("PAID", "PICKED_UP"):
        return FulfillResult(outcome="FULFILLED")

    if not manual:
        # Normal webhook/simulator callback
        if order_row["status"] != "RESERVED":
            return FulfillResult(outcome="UNFULFILLABLE", reason="TARGET_NOT_LIVE")

        if order_row["expires_at"] <= now:
            # Order expired. Mark status EXPIRED and release reserved stock once!
            updated = conn.execute(
                "UPDATE merch_orders SET status = 'EXPIRED' WHERE id = ? AND status = 'RESERVED';",
                (order_row["id"],),
            ).rowcount
            if updated == 1:
                items = conn.execute(
                    "SELECT variant_id, qty FROM merch_order_items WHERE order_id = ?;", (order_row["id"],)
                ).fetchall()
                for it in items:
                    conn.execute(
                        "UPDATE variants SET reserved_qty = reserved_qty - ? WHERE id = ?;",
                        (it["qty"], it["variant_id"]),
                    )
            return FulfillResult(outcome="UNFULFILLABLE", reason="TARGET_NOT_LIVE")

        # Guarded status update: RESERVED -> PAID
        updated = conn.execute(
            "UPDATE merch_orders SET status = 'PAID' WHERE id = ? AND status = 'RESERVED';",
            (order_row["id"],),
        ).rowcount
        if updated != 1:
            return FulfillResult(outcome="UNFULFILLABLE", reason="TARGET_NOT_LIVE")

        # Reserved stock remains reserved until pickup!
        return FulfillResult(outcome="FULFILLED")

    else:
        # Staff manual fulfillment of unfulfilled order (STO-06)
        if order_row["status"] not in ("RESERVED", "EXPIRED"):
            return FulfillResult(outcome="UNFULFILLABLE", reason="TARGET_NOT_LIVE")

        items = conn.execute(
            "SELECT variant_id, qty FROM merch_order_items WHERE order_id = ?;", (order_row["id"],)
        ).fetchall()

        if order_row["status"] == "EXPIRED" or order_row["expires_at"] <= now:
            # Re-reserve stock for late manual fulfillment
            for it in items:
                res = conn.execute(
                    "UPDATE variants SET reserved_qty = reserved_qty + ? "
                    "WHERE id = ? AND physical_qty - reserved_qty >= ?;",
                    (it["qty"], it["variant_id"], it["qty"]),
                ).rowcount
                if res != 1:
                    return FulfillResult(outcome="UNFULFILLABLE", reason="INSUFFICIENT_STOCK")

        # Guarded status update
        updated = conn.execute(
            "UPDATE merch_orders SET status = 'PAID' WHERE id = ? AND status IN ('RESERVED', 'EXPIRED');",
            (order_row["id"],),
        ).rowcount
        if updated != 1:
            return FulfillResult(outcome="UNFULFILLABLE", reason="TARGET_NOT_LIVE")

        return FulfillResult(outcome="FULFILLED")


def check_refundable_merch(conn: sqlite3.Connection, payment: Payment) -> None:
    """Verify merchandise order is eligible for refund per CONTRACT §1.5, STO-09."""
    order = conn.execute(
        "SELECT status FROM merch_orders WHERE id = ? OR payment_id = ?;",
        (payment.ref_id, payment.id),
    ).fetchone()

    if not order:
        raise DomainError("REFUND_BLOCKED", 409, "Merchandise order not found")

    if order["status"] == "PICKED_UP":
        raise DomainError("REFUND_BLOCKED", 409, "Cannot refund order after pickup")

    if order["status"] == "REFUNDED":
        raise DomainError("REFUND_BLOCKED", 409, "Order already refunded")

    if order["status"] != "PAID":
        raise DomainError("REFUND_BLOCKED", 409, f"Cannot refund order in status '{order['status']}'")


def apply_refund_merch(conn: sqlite3.Connection, payment: Payment, now: str) -> None:
    """Apply refund transitioning PAID -> REFUNDED and releasing reserved stock once (STO-09)."""
    order = conn.execute(
        "SELECT id, status FROM merch_orders WHERE id = ? OR payment_id = ?;",
        (payment.ref_id, payment.id),
    ).fetchone()
    if not order:
        return

    updated = conn.execute(
        "UPDATE merch_orders SET status = 'REFUNDED' WHERE id = ? AND status = 'PAID';",
        (order["id"],),
    ).rowcount
    if updated == 1:
        # Release reserved stock (physical stock is unchanged)
        items = conn.execute(
            "SELECT variant_id, qty FROM merch_order_items WHERE order_id = ?;", (order["id"],)
        ).fetchall()
        for it in items:
            conn.execute(
                "UPDATE variants SET reserved_qty = reserved_qty - ? WHERE id = ?;",
                (it["qty"], it["variant_id"]),
            )


def expire_orders(conn: sqlite3.Connection, as_of: str) -> int:
    """Expire orders exceeding their TTL and release reserved stock once per CONTRACT §1.5, STO-06."""
    expired_rows = conn.execute(
        "SELECT id FROM merch_orders WHERE status = 'RESERVED' AND expires_at <= ?;",
        (as_of,),
    ).fetchall()

    expired_count = 0
    for row in expired_rows:
        updated = conn.execute(
            "UPDATE merch_orders SET status = 'EXPIRED' WHERE id = ? AND status = 'RESERVED';",
            (row["id"],),
        ).rowcount
        if updated == 1:
            expired_count += 1
            items = conn.execute(
                "SELECT variant_id, qty FROM merch_order_items WHERE order_id = ?;", (row["id"],)
            ).fetchall()
            for it in items:
                conn.execute(
                    "UPDATE variants SET reserved_qty = reserved_qty - ? WHERE id = ?;",
                    (it["qty"], it["variant_id"]),
                )

    return expired_count


def mark_picked_up(conn: sqlite3.Connection, order_id: int, staff_id: int) -> None:
    """Staff pickup decreases both physical_qty and reserved_qty per CONTRACT §1.5, STO-07."""
    now_str = clock.now()
    order = conn.execute("SELECT status FROM merch_orders WHERE id = ?;", (order_id,)).fetchone()
    if not order:
        raise DomainError("NOT_FOUND", 404, "Order not found")

    if order["status"] == "RESERVED":
        raise DomainError("CONFLICT", 409, "Order is reserved but not yet paid")

    if order["status"] == "PICKED_UP":
        raise DomainError("CONFLICT", 409, "Order has already been picked up")

    if order["status"] in ("CANCELLED", "EXPIRED", "REFUNDED"):
        raise DomainError("CONFLICT", 409, f"Cannot pick up order in status '{order['status']}'")

    if order["status"] == "PAID":
        updated = conn.execute(
            "UPDATE merch_orders SET status = 'PICKED_UP', picked_up_at = ?, picked_up_by = ? "
            "WHERE id = ? AND status = 'PAID';",
            (now_str, staff_id, order_id),
        ).rowcount
        if updated != 1:
            raise DomainError("CONFLICT", 409, "Failed to update order status")

        # In the same transaction: both physical_qty and reserved_qty fall by qty
        items = conn.execute(
            "SELECT variant_id, qty FROM merch_order_items WHERE order_id = ?;", (order_id,)
        ).fetchall()
        for it in items:
            conn.execute(
                "UPDATE variants SET physical_qty = physical_qty - ?, reserved_qty = reserved_qty - ? "
                "WHERE id = ?;",
                (it["qty"], it["qty"], it["variant_id"]),
            )


def cancel_order(
    conn: sqlite3.Connection,
    handlers: Any,
    order_id: int,
    actor_id: int,
) -> None:
    """Cancel order: releases reserved stock if unpaid, or refunds via payment handler if paid."""
    order = conn.execute("SELECT * FROM merch_orders WHERE id = ?;", (order_id,)).fetchone()
    if not order:
        raise DomainError("NOT_FOUND", 404, "Order not found")

    if order["status"] == "CANCELLED":
        return  # idempotent

    if order["status"] == "RESERVED":
        updated = conn.execute(
            "UPDATE merch_orders SET status = 'CANCELLED' WHERE id = ? AND status = 'RESERVED';",
            (order_id,),
        ).rowcount
        if updated == 1:
            items = conn.execute(
                "SELECT variant_id, qty FROM merch_order_items WHERE order_id = ?;", (order_id,)
            ).fetchall()
            for it in items:
                conn.execute(
                    "UPDATE variants SET reserved_qty = reserved_qty - ? WHERE id = ?;",
                    (it["qty"], it["variant_id"]),
                )
    elif order["status"] == "PAID":
        from clubledger.payments.service import refund_payment

        actual_handlers = handlers or {"MERCH": MERCH_PURPOSE_HANDLER}
        if isinstance(actual_handlers, dict) and "MERCH" not in actual_handlers:
            actual_handlers["MERCH"] = MERCH_PURPOSE_HANDLER

        refund_payment(conn, actual_handlers, order["payment_id"], actor_id)
    else:
        raise DomainError("CONFLICT", 409, f"Cannot cancel order in status '{order['status']}'")


MERCH_PURPOSE_HANDLER = PurposeHandler(
    purpose="MERCH",
    fulfill=fulfill_merch_order,
    check_refundable=check_refundable_merch,
    apply_refund=apply_refund_merch,
)
