# In plain English: Reserves event capacity, issues tickets, checks admission and processes cancellation.
"""Events and ticketing service per CONTRACT.md §1.4, §2, §3.3, §13.3."""

import base64
from datetime import datetime, timezone
import hashlib
import secrets
import sqlite3
from typing import Any, Callable, Literal

from clubledger.core import clock
from clubledger.core.errors import DomainError
from clubledger.core.types import (
    CancelSummary,
    CheckInResult,
    EventReport,
    FulfillResult,
    Payment,
    PurposeHandler,
    TicketHold,
)

# Attempt to import genuine A-owned pricing and payments
try:
    from clubledger.core.pricing import active_membership as _genuine_active_membership
    from clubledger.core.pricing import ticket_price as _genuine_ticket_price
except ImportError:
    _genuine_active_membership = None
    _genuine_ticket_price = None

try:
    from clubledger.payments.service import create_payment as _genuine_create_payment
except ImportError:
    _genuine_create_payment = None


class DependencyBlockerError(DomainError):
    """Raised when an A-owned or D-owned dependency is not yet implemented."""

    def __init__(self, message: str) -> None:
        super().__init__("DEPENDENCY_BLOCKER", 503, message)


def seed_events(conn: sqlite3.Connection) -> None:
    """Seed demo events per CONTRACT defaults."""
    exists = conn.execute("SELECT 1 FROM events LIMIT 1;").fetchone()
    if not exists:
        # Resolve an open term
        term_row = conn.execute(
            "SELECT id FROM terms WHERE status = 'OPEN' LIMIT 1;"
        ).fetchone()
        term_id = term_row["id"] if term_row else 1
        now_str = clock.now()
        conn.execute(
            "INSERT INTO events ("
            "  id, term_id, title, venue, starts_at, ends_at, capacity, "
            "  member_price_paise, public_price_paise, max_per_order, status, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ON_SALE', ?);",
            (
                1,
                term_id,
                "Spring Gala 2027",
                "Grand Auditorium",
                "2027-03-15T18:00:00Z",
                "2027-03-15T22:00:00Z",
                100,
                80000,
                100000,
                4,
                now_str,
            ),
        )


def _compute_ticket_price_fallback(
    conn: sqlite3.Connection,
    event_row: sqlite3.Row,
    user_id: int,
    now_str: str,
) -> tuple[int, Literal["MEMBER", "PUBLIC"]]:
    """Fallback price calculation adhering strictly to CONTRACT §2 if pricing module is not loaded."""
    mem = conn.execute(
        "SELECT m.id, p.ticket_discount_bps "
        "FROM memberships m "
        "JOIN membership_plans p ON m.plan_id = p.id "
        "WHERE m.user_id = ? AND m.status = 'ACTIVE' "
        "  AND m.starts_at <= ? AND m.expires_at > ? "
        "ORDER BY m.id DESC LIMIT 1;",
        (user_id, now_str, now_str),
    ).fetchone()

    pub_price = event_row["public_price_paise"]
    mem_base_price = event_row["member_price_paise"]

    if mem:
        discount_bps = mem["ticket_discount_bps"]
        discounted = pub_price * (10000 - discount_bps) // 10000
        final_member_price = min(mem_base_price, discounted)
        return (final_member_price, "MEMBER")

    return (pub_price, "PUBLIC")


def get_available_seats(
    conn: sqlite3.Connection, event_id: int, capacity: int, now_str: str
) -> int:
    """Calculate available seats per CONTRACT §1.4: capacity - (HELD with expires_at > now + ISSUED/USED tickets)."""
    held_qty = conn.execute(
        "SELECT COALESCE(SUM(qty), 0) AS total_held FROM ticket_holds "
        "WHERE event_id = ? AND status = 'HELD' AND expires_at > ?;",
        (event_id, now_str),
    ).fetchone()["total_held"]

    taken_tickets = conn.execute(
        "SELECT COUNT(*) AS total_taken FROM tickets "
        "WHERE event_id = ? AND status IN ('ISSUED', 'USED');",
        (event_id,),
    ).fetchone()["total_taken"]

    return max(0, capacity - (held_qty + taken_tickets))


def create_hold(
    conn: sqlite3.Connection,
    user_id: int,
    event_id: int,
    qty: int,
    idempotency_key: str,
    *,
    pricing_fn: Callable[..., tuple[int, Literal["MEMBER", "PUBLIC"]]] | None = None,
    create_payment_fn: Callable[..., Payment] | None = None,
) -> tuple[TicketHold, Payment | None]:
    """Create a capacity-safe hold or issue free tickets per CONTRACT §1.4, §2, §6, §13.3."""
    now_str = clock.now()

    # 1. Validate user
    user_row = conn.execute(
        "SELECT id, is_active FROM users WHERE id = ?;", (user_id,)
    ).fetchone()
    if not user_row or not user_row["is_active"]:
        raise DomainError("NOT_FOUND", 404, "Active user not found")

    # 2. Check idempotency key before status or capacity checks to support clean replay
    req_hash = hashlib.sha256(
        f"event_id={event_id}&qty={qty}".encode("utf-8")
    ).hexdigest()
    existing_key = conn.execute(
        "SELECT request_hash, result_ref FROM idempotency_keys WHERE actor_user_id = ? AND action = 'ticket.hold' AND key = ?;",
        (user_id, idempotency_key),
    ).fetchone()
    if existing_key:
        if existing_key["request_hash"] != req_hash:
            raise DomainError(
                "IDEMPOTENCY_CONFLICT",
                422,
                "Idempotency key reused with different request parameters",
            )

        ref = existing_key["result_ref"]
        # Format: hold:{hold_id}:free or hold:{hold_id}:pay:{payment_id}
        parts = ref.split(":")
        hold_id = int(parts[1])
        h_row = conn.execute(
            "SELECT * FROM ticket_holds WHERE id = ?;", (hold_id,)
        ).fetchone()
        if not h_row:
            raise DomainError("NOT_FOUND", 404, "Previous hold not found")

        hold_obj = TicketHold(
            id=h_row["id"],
            event_id=h_row["event_id"],
            user_id=h_row["user_id"],
            qty=h_row["qty"],
            unit_price_paise=h_row["unit_price_paise"],
            price_tier=h_row["price_tier"],
            status=h_row["status"],
            expires_at=h_row["expires_at"],
            created_at=h_row["created_at"],
        )
        if len(parts) >= 4 and parts[2] == "pay":
            pay_id = int(parts[3])
            p_row = conn.execute(
                "SELECT * FROM payments WHERE id = ?;", (pay_id,)
            ).fetchone()
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
            return (hold_obj, payment_obj)
        return (hold_obj, None)

    # 3. Validate event
    event_row = conn.execute(
        "SELECT * FROM events WHERE id = ?;", (event_id,)
    ).fetchone()
    if not event_row:
        raise DomainError("NOT_FOUND", 404, "Event not found")
    if event_row["status"] != "ON_SALE":
        raise DomainError(
            "SOLD_OUT", 409, f"Event is {event_row['status']}, not on sale"
        )

    # 4. Validate quantity
    max_order = event_row["max_per_order"]
    if qty < 1 or qty > max_order:
        raise DomainError(
            "VALIDATION", 422, f"Quantity must be between 1 and {max_order}"
        )

    # 5. Check capacity invariant inside transaction
    available = get_available_seats(conn, event_id, event_row["capacity"], now_str)
    if available < qty:
        raise DomainError("SOLD_OUT", 409, f"Only {available} seats remaining")

    # 6. Determine unit price server-side
    pricer = pricing_fn or _genuine_ticket_price
    if pricer is not None:
        unit_price, price_tier = pricer(conn, event_id, user_id, now_str)
    else:
        unit_price, price_tier = _compute_ticket_price_fallback(
            conn, event_row, user_id, now_str
        )

    # 7. Branch: Free ticket (unit_price == 0) vs Paid ticket
    if unit_price == 0:
        # Free tickets: hold is created already CONSUMED; issues tickets immediately
        cur = conn.execute(
            "INSERT INTO ticket_holds ("
            "  event_id, user_id, qty, unit_price_paise, price_tier, status, "
            "  expires_at, released_at, consumed_at, created_at"
            ") VALUES (?, ?, ?, 0, ?, 'CONSUMED', ?, NULL, ?, ?);",
            (event_id, user_id, qty, price_tier, now_str, now_str, now_str),
        )
        hold_id = cur.lastrowid
        assert hold_id is not None

        # Create N tickets (seat_index 1..qty) with payment_id = NULL
        for seat in range(1, qty + 1):
            code_rand = (
                base64.b32encode(secrets.token_bytes(10)).decode("ascii").rstrip("=")
            )
            code = f"TKT-{hold_id:04d}-{seat}-{code_rand}"
            conn.execute(
                "INSERT INTO tickets ("
                "  event_id, hold_id, seat_index, user_id, payment_id, code, "
                "  price_paise, price_tier, status, used_at, used_by, created_at"
                ") VALUES (?, ?, ?, ?, NULL, ?, 0, ?, 'ISSUED', NULL, NULL, ?);",
                (event_id, hold_id, seat, user_id, code, price_tier, now_str),
            )

        conn.execute(
            "INSERT INTO idempotency_keys (actor_user_id, action, key, request_hash, result_ref, created_at) "
            "VALUES (?, 'ticket.hold', ?, ?, ?, ?);",
            (user_id, idempotency_key, req_hash, f"hold:{hold_id}:free", now_str),
        )

        hold_obj = TicketHold(
            id=hold_id,
            event_id=event_id,
            user_id=user_id,
            qty=qty,
            unit_price_paise=0,
            price_tier=price_tier,
            status="CONSUMED",
            expires_at=now_str,
            created_at=now_str,
        )
        return (hold_obj, None)

    # Paid ticket: Hold TTL = 10 minutes (600 s)
    from datetime import timedelta

    now_dt = datetime.fromisoformat(now_str.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )
    expires_dt = now_dt + timedelta(seconds=600)
    expires_str = expires_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    cur = conn.execute(
        "INSERT INTO ticket_holds ("
        "  event_id, user_id, qty, unit_price_paise, price_tier, status, "
        "  expires_at, released_at, consumed_at, created_at"
        ") VALUES (?, ?, ?, ?, ?, 'HELD', ?, NULL, NULL, ?);",
        (event_id, user_id, qty, unit_price, price_tier, expires_str, now_str),
    )
    hold_id = cur.lastrowid
    assert hold_id is not None

    total_paise = qty * unit_price
    payment_creator = create_payment_fn or _genuine_create_payment
    if payment_creator is None:
        raise DependencyBlockerError(
            "payments.service.create_payment is not yet available; dependency blocker per BUILD_ORDER"
        )

    payment = payment_creator(
        conn,
        user_id=user_id,
        purpose="TICKET",
        ref_table="ticket_holds",
        ref_id=hold_id,
        amount_paise=total_paise,
    )

    conn.execute(
        "INSERT INTO idempotency_keys (actor_user_id, action, key, request_hash, result_ref, created_at) "
        "VALUES (?, 'ticket.hold', ?, ?, ?, ?);",
        (
            user_id,
            idempotency_key,
            req_hash,
            f"hold:{hold_id}:pay:{payment.id}",
            now_str,
        ),
    )

    hold_obj = TicketHold(
        id=hold_id,
        event_id=event_id,
        user_id=user_id,
        qty=qty,
        unit_price_paise=unit_price,
        price_tier=price_tier,
        status="HELD",
        expires_at=expires_str,
        created_at=now_str,
    )
    return (hold_obj, payment)


def fulfill_ticket_hold(
    conn: sqlite3.Connection,
    payment: Payment,
    *,
    manual: bool,
    now: str,
) -> FulfillResult:
    """Fulfill ticket hold transitioning HELD -> CONSUMED and generating N tickets per CONTRACT §1.4."""
    hold_row = conn.execute(
        "SELECT * FROM ticket_holds WHERE id = ?;", (payment.ref_id,)
    ).fetchone()
    if not hold_row:
        return FulfillResult(outcome="UNFULFILLABLE", reason="TARGET_NOT_LIVE")

    # Idempotent replay: already CONSUMED
    if hold_row["status"] == "CONSUMED":
        return FulfillResult(outcome="FULFILLED")

    # Check event eligibility: event must exist and not be CANCELLED
    event_row = conn.execute(
        "SELECT status, capacity FROM events WHERE id = ?;", (hold_row["event_id"],)
    ).fetchone()
    if not event_row or event_row["status"] == "CANCELLED":
        return FulfillResult(outcome="UNFULFILLABLE", reason="TARGET_NOT_LIVE")

    if not manual:
        # Normal callback: hold must be HELD and not expired
        if hold_row["status"] != "HELD":
            return FulfillResult(outcome="UNFULFILLABLE", reason="TARGET_NOT_LIVE")

        if hold_row["expires_at"] <= now:
            # Hold expired past TTL. Mark status EXPIRED and return UNFULFILLABLE without consuming capacity.
            conn.execute(
                "UPDATE ticket_holds SET status = 'EXPIRED' WHERE id = ? AND status = 'HELD';",
                (hold_row["id"],),
            )
            return FulfillResult(outcome="UNFULFILLABLE", reason="TARGET_NOT_LIVE")

        # Guarded status update: exactly 1 row affected
        updated = conn.execute(
            "UPDATE ticket_holds SET status = 'CONSUMED', consumed_at = ? "
            "WHERE id = ? AND status = 'HELD';",
            (now, hold_row["id"]),
        ).rowcount
        if updated != 1:
            return FulfillResult(outcome="UNFULFILLABLE", reason="TARGET_NOT_LIVE")

    else:
        # Manual staff fulfillment: allowed for HELD or EXPIRED holds
        if hold_row["status"] not in ("HELD", "EXPIRED"):
            return FulfillResult(outcome="UNFULFILLABLE", reason="TARGET_NOT_LIVE")

        # Capacity check: if hold is EXPIRED or has passed expires_at, re-check live capacity
        if hold_row["status"] == "EXPIRED" or hold_row["expires_at"] <= now:
            avail = get_available_seats(
                conn, hold_row["event_id"], event_row["capacity"], now
            )
            if avail < hold_row["qty"]:
                return FulfillResult(outcome="UNFULFILLABLE", reason="SOLD_OUT")

        # Guarded status update: exactly 1 row affected
        updated = conn.execute(
            "UPDATE ticket_holds SET status = 'CONSUMED', consumed_at = ? "
            "WHERE id = ? AND status IN ('HELD', 'EXPIRED');",
            (now, hold_row["id"]),
        ).rowcount
        if updated != 1:
            return FulfillResult(outcome="UNFULFILLABLE", reason="TARGET_NOT_LIVE")

    # Issue N tickets with UNIQUE(hold_id, seat_index)
    qty = hold_row["qty"]
    unit_price = hold_row["unit_price_paise"]
    tier = hold_row["price_tier"]
    event_id = hold_row["event_id"]
    user_id = hold_row["user_id"]

    for seat in range(1, qty + 1):
        code_rand = (
            base64.b32encode(secrets.token_bytes(10)).decode("ascii").rstrip("=")
        )
        code = f"TKT-{hold_row['id']:04d}-{seat}-{code_rand}"
        conn.execute(
            "INSERT INTO tickets ("
            "  event_id, hold_id, seat_index, user_id, payment_id, code, "
            "  price_paise, price_tier, status, used_at, used_by, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ISSUED', NULL, NULL, ?);",
            (
                event_id,
                hold_row["id"],
                seat,
                user_id,
                payment.id,
                code,
                unit_price,
                tier,
                now,
            ),
        )

    return FulfillResult(outcome="FULFILLED")


def check_refundable_tickets(conn: sqlite3.Connection, payment: Payment) -> None:
    """Verify tickets can be refunded per CONTRACT §1.4 and §3.3."""
    tickets = conn.execute(
        "SELECT status FROM tickets WHERE payment_id = ?;", (payment.id,)
    ).fetchall()
    if not tickets:
        raise DomainError("REFUND_BLOCKED", 409, "No tickets found for payment")

    if any(t["status"] == "USED" for t in tickets):
        raise DomainError(
            "REFUND_BLOCKED", 409, "Cannot refund payment with used tickets"
        )

    if all(t["status"] == "REFUNDED" for t in tickets):
        raise DomainError("REFUND_BLOCKED", 409, "Tickets already refunded")


def apply_refund_tickets(conn: sqlite3.Connection, payment: Payment, now: str) -> None:
    """Transition tickets to REFUNDED per CONTRACT §3.3."""
    conn.execute(
        "UPDATE tickets SET status = 'REFUNDED' WHERE payment_id = ? AND status = 'ISSUED';",
        (payment.id,),
    )


def expire_holds(conn: sqlite3.Connection, as_of: str) -> int:
    """Expire holds exceeding their TTL per CONTRACT §1.4."""
    cur = conn.execute(
        "UPDATE ticket_holds SET status = 'EXPIRED' WHERE status = 'HELD' AND expires_at <= ?;",
        (as_of,),
    )
    return cur.rowcount


def check_in(
    conn: sqlite3.Connection, event_id: int, code: str, staff_id: int
) -> CheckInResult:
    """Staff check-in for ticket code per CONTRACT §1.4 and EVT-07."""
    clean_code = code.strip()
    ticket = conn.execute(
        "SELECT id, event_id, status, used_at FROM tickets WHERE code = ?;",
        (clean_code,),
    ).fetchone()

    if not ticket:
        return CheckInResult(status="REJECTED", message="Ticket code not found")

    if ticket["event_id"] != event_id:
        return CheckInResult(status="REJECTED", message="Ticket is for another event")

    if ticket["status"] == "USED":
        return CheckInResult(
            status="ALREADY_USED",
            message=f"Ticket already used at {ticket['used_at']}",
            ticket_id=ticket["id"],
        )

    if ticket["status"] in ("REFUNDED", "VOID"):
        return CheckInResult(
            status="REJECTED",
            message=f"Ticket is {ticket['status']}",
            ticket_id=ticket["id"],
        )

    if ticket["status"] == "ISSUED":
        now_str = clock.now()
        updated = conn.execute(
            "UPDATE tickets SET status = 'USED', used_at = ?, used_by = ? "
            "WHERE id = ? AND status = 'ISSUED';",
            (now_str, staff_id, ticket["id"]),
        ).rowcount
        if updated == 1:
            return CheckInResult(
                status="OK", message="Check-in confirmed", ticket_id=ticket["id"]
            )

    return CheckInResult(status="REJECTED", message="Invalid ticket status")


def cancel_event(
    conn: sqlite3.Connection,
    handlers: Any,
    event_id: int,
    actor_id: int,
) -> CancelSummary:
    """Cancel event: void free tickets, refund eligible paid tickets through refund_payment per CONTRACT §3.3."""
    conn.execute("UPDATE events SET status = 'CANCELLED' WHERE id = ?;", (event_id,))

    # Free tickets become VOID
    conn.execute(
        "UPDATE tickets SET status = 'VOID' WHERE event_id = ? AND payment_id IS NULL AND status = 'ISSUED';",
        (event_id,),
    )
    void_count = conn.execute(
        "SELECT COUNT(*) AS c FROM tickets WHERE event_id = ? AND payment_id IS NULL AND status = 'VOID';",
        (event_id,),
    ).fetchone()["c"]

    # Identify payments for this event
    payments = conn.execute(
        "SELECT DISTINCT payment_id FROM tickets WHERE event_id = ? AND payment_id IS NOT NULL;",
        (event_id,),
    ).fetchall()

    refunded_count = 0
    flagged_count = 0

    actual_handlers: dict[str, Any] = {}
    if handlers is not None:
        if isinstance(handlers, dict):
            actual_handlers.update(handlers)
        elif hasattr(handlers, "items"):
            actual_handlers.update(dict(handlers))
    if "TICKET" not in actual_handlers:
        actual_handlers["TICKET"] = TICKET_PURPOSE_HANDLER

    from clubledger.payments.service import refund_payment

    for p in payments:
        pid = p["payment_id"]
        # Check if any ticket under this payment is USED
        has_used = conn.execute(
            "SELECT 1 FROM tickets WHERE payment_id = ? AND status = 'USED' LIMIT 1;",
            (pid,),
        ).fetchone()
        if has_used:
            # Used tickets go to manual review; cannot refund payment
            flagged_count += 1
            continue

        pay_row = conn.execute(
            "SELECT status FROM payments WHERE id = ?;", (pid,)
        ).fetchone()
        if not pay_row:
            continue

        if pay_row["status"] == "REFUNDED":
            # Idempotent repeat cancellation
            refunded_count += 1
            continue

        if pay_row["status"] == "SUCCEEDED":
            try:
                refund_payment(conn, actual_handlers, pid, actor_id)
                refunded_count += 1
            except Exception:
                flagged_count += 1
        else:
            flagged_count += 1

    return CancelSummary(
        event_id=event_id,
        refunded_count=refunded_count,
        void_count=void_count,
        flagged_count=flagged_count,
    )


def event_report(conn: sqlite3.Connection, event_id: int) -> EventReport:
    """Generate event report per CONTRACT §1.4, §11, EVT-09."""
    sold = conn.execute(
        "SELECT COUNT(*) AS c FROM tickets WHERE event_id = ? AND status IN ('ISSUED', 'USED');",
        (event_id,),
    ).fetchone()["c"]

    attended = conn.execute(
        "SELECT COUNT(*) AS c FROM tickets WHERE event_id = ? AND status = 'USED';",
        (event_id,),
    ).fetchone()["c"]

    no_shows = max(0, sold - attended)

    # Gross must sum tickets over ISSUED, USED, and REFUNDED per CONTRACT §11
    gross = conn.execute(
        "SELECT COALESCE(SUM(price_paise), 0) AS g FROM tickets WHERE event_id = ? AND status IN ('ISSUED', 'USED', 'REFUNDED');",
        (event_id,),
    ).fetchone()["g"]

    refunded = conn.execute(
        "SELECT COALESCE(SUM(price_paise), 0) AS r FROM tickets WHERE event_id = ? AND status = 'REFUNDED';",
        (event_id,),
    ).fetchone()["r"]

    net_proceeds = gross - refunded

    return EventReport(
        event_id=event_id,
        sold=sold,
        attended=attended,
        no_shows=no_shows,
        gross=gross,
        refunded=refunded,
        net_proceeds=net_proceeds,
    )


TICKET_PURPOSE_HANDLER = PurposeHandler(
    purpose="TICKET",
    fulfill=fulfill_ticket_hold,
    check_refundable=check_refundable_tickets,
    apply_refund=apply_refund_tickets,
)
