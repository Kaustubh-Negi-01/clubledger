"""Payment service per CONTRACT.md §1.2, §3.1, §5, §7, §8, and §13.3."""

from datetime import datetime, timezone, timedelta
import hashlib
import json
import secrets
import sqlite3
from typing import Any, Literal

from clubledger.core import clock
from clubledger.core.errors import DomainError
from clubledger.core.types import EventOutcome, Handlers, Payment


def _get_journal_service(journal: Any = None) -> Any:
    if journal is not None:
        return journal
    try:
        from clubledger.journal import service as journal_svc
        return journal_svc
    except ImportError:
        return None


def _post_payment_received_safe(
    conn: sqlite3.Connection, journal: Any, payment: Payment, *, fulfilled: bool
) -> int | None:
    svc = _get_journal_service(journal)
    if svc and hasattr(svc, "post_payment_received"):
        return svc.post_payment_received(conn, payment, fulfilled=fulfilled)
    return None


def _post_payment_late_fulfilled_safe(
    conn: sqlite3.Connection, journal: Any, payment: Payment
) -> int | None:
    svc = _get_journal_service(journal)
    if svc and hasattr(svc, "post_payment_late_fulfilled"):
        return svc.post_payment_late_fulfilled(conn, payment)
    return None


def _post_receipt_event_safe(conn: sqlite3.Connection, journal: Any, event_row: Any) -> int | None:
    svc = _get_journal_service(journal)
    if svc and hasattr(svc, "post_receipt_event"):
        return svc.post_receipt_event(conn, event_row)
    return None


def _post_settlement_safe(
    conn: sqlite3.Connection, journal: Any, source_type: str, source_id: int, amount_paise: int
) -> int | None:
    svc = _get_journal_service(journal)
    if svc and hasattr(svc, "post_settlement"):
        return svc.post_settlement(conn, source_type, source_id, amount_paise)
    return None


def _reverse_all_for_source_safe(
    conn: sqlite3.Connection, journal: Any, source_type: str, source_id: int, memo: str
) -> list[int]:
    svc = _get_journal_service(journal)
    if svc and hasattr(svc, "reverse_all_for_source"):
        return svc.reverse_all_for_source(conn, source_type, source_id, memo)
    return []


def create_payment(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    purpose: str,
    ref_table: str,
    ref_id: int,
    amount_paise: int,
) -> Payment:
    """Create a new payment row per CONTRACT §1.2 and §13.3."""
    if amount_paise <= 0:
        raise DomainError("VALIDATION", 422, "Amount must be positive")

    purpose_upper = purpose.upper()
    if purpose_upper not in {"DUES", "TICKET", "MERCH"}:
        raise DomainError("VALIDATION", 422, f"Invalid purpose: {purpose}")

    if ref_table not in {"memberships", "ticket_holds", "merch_orders"}:
        raise DomainError("VALIDATION", 422, f"Invalid ref_table: {ref_table}")

    # Verify user exists and is active
    user = conn.execute("SELECT id, is_active FROM users WHERE id = ?;", (user_id,)).fetchone()
    if not user:
        raise DomainError("NOT_FOUND", 404, "User not found")
    if user["is_active"] != 1:
        raise DomainError("VALIDATION", 422, "User account is not active")

    # Get current OPEN term
    term = conn.execute("SELECT id FROM terms WHERE status = 'OPEN';").fetchone()
    if not term:
        raise DomainError("TERM_CLOSED", 409, "No open financial term")

    public_id = f"pay_{secrets.token_urlsafe(16)}"
    now = clock.now()

    cur = conn.execute(
        """
        INSERT INTO payments (
            public_id, user_id, purpose, ref_table, ref_id,
            amount_paise, currency, status, fulfillment, term_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'INR', 'CREATED', 'NONE', ?, ?);
        """,
        (
            public_id,
            user_id,
            purpose_upper,
            ref_table,
            ref_id,
            amount_paise,
            term["id"],
            now,
        ),
    )

    return Payment(
        id=cur.lastrowid,  # type: ignore[arg-type]
        public_id=public_id,
        user_id=user_id,
        purpose=purpose_upper,
        ref_table=ref_table,
        ref_id=ref_id,
        amount_paise=amount_paise,
        status="CREATED",
        fulfillment="NONE",
        term_id=term["id"],
    )


def handle_event(
    conn: sqlite3.Connection,
    handlers: Handlers,
    raw_body: bytes,
    signature_header: str,
    now: str,
    journal: Any = None,
) -> EventOutcome:
    """Trusted phase of event processing per CONTRACT §3.1, §5, §13.3."""
    body_sha256 = hashlib.sha256(raw_body).hexdigest()
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise DomainError("VALIDATION", 400, "Invalid JSON body")

    event_id = str(payload.get("event_id", ""))
    event_type = str(payload.get("type", ""))
    claimed_public_id = str(payload.get("payment_id", ""))
    claimed_user_id = payload.get("user_id")
    amount_paise = payload.get("amount_paise")
    currency = str(payload.get("currency", ""))

    # 1. Check existing event_id
    existing = conn.execute(
        "SELECT id, outcome, reason, payment_id, body_sha256 FROM payment_events WHERE event_id = ?;",
        (event_id,),
    ).fetchone()
    if existing:
        if existing["body_sha256"] == body_sha256:
            # Replay with identical body -> return stored outcome without DB write
            return EventOutcome(
                event_row_id=existing["id"],
                outcome=existing["outcome"],
                reason=existing["reason"],
                payment_id=existing["payment_id"],
                http_status=200,
            )
        # Same event_id with different body -> 409 EVENT_ID_REUSED
        raise DomainError("EVENT_ID_REUSED", 409, "Event ID already used with different body")

    # 2. Payment lookup by claimed_public_id
    payment_row = conn.execute(
        "SELECT * FROM payments WHERE public_id = ?;",
        (claimed_public_id,),
    ).fetchone()

    # Case A: Unknown payment
    if not payment_row:
        outcome = "UNAPPLIED_RECEIPT"
        reason = "UNKNOWN_PAYMENT"
        cur = conn.execute(
            """
            INSERT INTO payment_events (
                event_id, body_sha256, raw_body, type, payment_id,
                claimed_user_id, claimed_public_id, amount_paise, currency,
                outcome, reason, created_at
            ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                event_id,
                body_sha256,
                raw_body.decode("utf-8"),
                event_type,
                claimed_user_id,
                claimed_public_id,
                amount_paise if isinstance(amount_paise, int) else 0,
                currency,
                outcome,
                reason,
                now,
            ),
        )
        event_row_id = cur.lastrowid
        if (
            event_type == "payment.succeeded"
            and currency == "INR"
            and isinstance(amount_paise, int)
            and amount_paise > 0
        ):
            _post_receipt_event_safe(
                conn, journal, {"id": event_row_id, "amount_paise": amount_paise, "currency": currency}
            )
        return EventOutcome(
            event_row_id=event_row_id,  # type: ignore[arg-type]
            outcome=outcome,
            reason=reason,
            payment_id=None,
            http_status=200,
        )

    payment_id = payment_row["id"]

    # Case B: Identity/amount/currency mismatch
    mismatch_reason = None
    if currency != "INR":
        mismatch_reason = "CURRENCY_MISMATCH"
    elif claimed_user_id is not None and claimed_user_id != payment_row["user_id"]:
        mismatch_reason = "USER_MISMATCH"
    elif amount_paise != payment_row["amount_paise"]:
        mismatch_reason = "AMOUNT_MISMATCH"

    if mismatch_reason:
        outcome = "UNAPPLIED_RECEIPT"
        reason = mismatch_reason
        cur = conn.execute(
            """
            INSERT INTO payment_events (
                event_id, body_sha256, raw_body, type, payment_id,
                claimed_user_id, claimed_public_id, amount_paise, currency,
                outcome, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                event_id,
                body_sha256,
                raw_body.decode("utf-8"),
                event_type,
                payment_id,
                claimed_user_id,
                claimed_public_id,
                amount_paise if isinstance(amount_paise, int) else 0,
                currency,
                outcome,
                reason,
                now,
            ),
        )
        event_row_id = cur.lastrowid
        if (
            event_type == "payment.succeeded"
            and currency == "INR"
            and isinstance(amount_paise, int)
            and amount_paise > 0
        ):
            _post_receipt_event_safe(
                conn, journal, {"id": event_row_id, "amount_paise": amount_paise, "currency": currency}
            )
        return EventOutcome(
            event_row_id=event_row_id,  # type: ignore[arg-type]
            outcome=outcome,
            reason=reason,
            payment_id=payment_id,
            http_status=200,
        )

    # Case C: Failed event
    if event_type == "payment.failed":
        if payment_row["status"] in ("CREATED", "PENDING"):
            conn.execute("UPDATE payments SET status = 'FAILED' WHERE id = ?;", (payment_id,))
            outcome = "APPLIED"
            reason = None
        else:
            outcome = "NO_EFFECT"
            reason = f"PAYMENT_{payment_row['status']}"

        cur = conn.execute(
            """
            INSERT INTO payment_events (
                event_id, body_sha256, raw_body, type, payment_id,
                claimed_user_id, claimed_public_id, amount_paise, currency,
                outcome, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                event_id,
                body_sha256,
                raw_body.decode("utf-8"),
                event_type,
                payment_id,
                claimed_user_id,
                claimed_public_id,
                amount_paise,
                currency,
                outcome,
                reason,
                now,
            ),
        )
        return EventOutcome(
            event_row_id=cur.lastrowid,  # type: ignore[arg-type]
            outcome=outcome,
            reason=reason,
            payment_id=payment_id,
            http_status=200,
        )

    # Case D: Succeeded event matching identity, user, amount, currency
    payment = Payment(
        id=payment_row["id"],
        public_id=payment_row["public_id"],
        user_id=payment_row["user_id"],
        purpose=payment_row["purpose"],
        ref_table=payment_row["ref_table"],
        ref_id=payment_row["ref_id"],
        amount_paise=payment_row["amount_paise"],
        status=payment_row["status"],
        fulfillment=payment_row["fulfillment"],
        term_id=payment_row["term_id"],
    )

    # D1: Already SUCCEEDED or REFUNDED -> REPEATED_NOTIFICATION / NO_EFFECT
    if payment_row["status"] in ("SUCCEEDED", "REFUNDED"):
        outcome = "NO_EFFECT"
        reason = "REPEATED_NOTIFICATION"
        cur = conn.execute(
            """
            INSERT INTO payment_events (
                event_id, body_sha256, raw_body, type, payment_id,
                claimed_user_id, claimed_public_id, amount_paise, currency,
                outcome, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                event_id,
                body_sha256,
                raw_body.decode("utf-8"),
                event_type,
                payment_id,
                claimed_user_id,
                claimed_public_id,
                amount_paise,
                currency,
                outcome,
                reason,
                now,
            ),
        )
        return EventOutcome(
            event_row_id=cur.lastrowid,  # type: ignore[arg-type]
            outcome=outcome,
            reason=reason,
            payment_id=payment_id,
            http_status=200,
        )

    # Check if payment's creation term is CLOSED
    term_row = conn.execute("SELECT status FROM terms WHERE id = ?;", (payment.term_id,)).fetchone()
    is_closed_term = term_row and term_row["status"] == "CLOSED"

    if payment_row["status"] == "EXPIRED":
        outcome = "APPLIED_UNFULFILLED"
        reason = "LATE_AFTER_EXPIRED"
        conn.execute(
            "UPDATE payments SET status = 'SUCCEEDED', fulfillment = 'UNFULFILLED', succeeded_at = ? WHERE id = ?;",
            (now, payment_id),
        )
        _post_payment_received_safe(conn, journal, payment, fulfilled=False)
    elif payment_row["status"] == "FAILED":
        outcome = "APPLIED_UNFULFILLED"
        reason = "LATE_AFTER_FAILED"
        conn.execute(
            "UPDATE payments SET status = 'SUCCEEDED', fulfillment = 'UNFULFILLED', succeeded_at = ? WHERE id = ?;",
            (now, payment_id),
        )
        _post_payment_received_safe(conn, journal, payment, fulfilled=False)
    elif is_closed_term:
        outcome = "APPLIED_UNFULFILLED"
        reason = "CLOSED_TERM"
        conn.execute(
            "UPDATE payments SET status = 'SUCCEEDED', fulfillment = 'UNFULFILLED', succeeded_at = ? WHERE id = ?;",
            (now, payment_id),
        )
        _post_payment_received_safe(conn, journal, payment, fulfilled=False)
    else:
        # Status is CREATED or PENDING, term is OPEN: Attempt fulfillment
        handler = handlers.get(payment.purpose)
        if not handler:
            outcome = "APPLIED_UNFULFILLED"
            reason = "UNSUPPORTED_PURPOSE"
            conn.execute(
                "UPDATE payments SET status = 'SUCCEEDED', fulfillment = 'UNFULFILLED', succeeded_at = ? WHERE id = ?;",
                (now, payment_id),
            )
            _post_payment_received_safe(conn, journal, payment, fulfilled=False)
        else:
            fulfill_res = handler.fulfill(conn, payment, manual=False, now=now)
            if fulfill_res.outcome == "FULFILLED":
                outcome = "APPLIED"
                reason = None
                conn.execute(
                    "UPDATE payments SET status = 'SUCCEEDED', fulfillment = 'FULFILLED', succeeded_at = ? WHERE id = ?;",
                    (now, payment_id),
                )
                _post_payment_received_safe(conn, journal, payment, fulfilled=True)
            else:
                outcome = "APPLIED_UNFULFILLED"
                reason = fulfill_res.reason or "UNFULFILLABLE"
                conn.execute(
                    "UPDATE payments SET status = 'SUCCEEDED', fulfillment = 'UNFULFILLED', succeeded_at = ? WHERE id = ?;",
                    (now, payment_id),
                )
                _post_payment_received_safe(conn, journal, payment, fulfilled=False)

    cur = conn.execute(
        """
        INSERT INTO payment_events (
            event_id, body_sha256, raw_body, type, payment_id,
            claimed_user_id, claimed_public_id, amount_paise, currency,
            outcome, reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            event_id,
            body_sha256,
            raw_body.decode("utf-8"),
            event_type,
            payment_id,
            claimed_user_id,
            claimed_public_id,
            amount_paise,
            currency,
            outcome,
            reason,
            now,
        ),
    )
    return EventOutcome(
        event_row_id=cur.lastrowid,  # type: ignore[arg-type]
        outcome=outcome,
        reason=reason,
        payment_id=payment_id,
        http_status=200,
    )


def refund_payment(
    conn: sqlite3.Connection,
    handlers: Handlers,
    payment_id: int,
    actor_id: int,
    journal: Any = None,
) -> None:
    """Issue a full refund for a SUCCEEDED payment per CONTRACT §8."""
    payment_row = conn.execute("SELECT * FROM payments WHERE id = ?;", (payment_id,)).fetchone()
    if not payment_row:
        raise DomainError("NOT_FOUND", 404, f"Payment {payment_id} not found")

    if payment_row["status"] != "SUCCEEDED":
        raise DomainError(
            "REFUND_BLOCKED",
            409,
            f"Cannot refund payment with status '{payment_row['status']}'",
        )

    now = clock.now()
    payment = Payment(
        id=payment_row["id"],
        public_id=payment_row["public_id"],
        user_id=payment_row["user_id"],
        purpose=payment_row["purpose"],
        ref_table=payment_row["ref_table"],
        ref_id=payment_row["ref_id"],
        amount_paise=payment_row["amount_paise"],
        status=payment_row["status"],
        fulfillment=payment_row["fulfillment"],
        term_id=payment_row["term_id"],
    )

    if payment_row["fulfillment"] == "UNFULFILLED":
        # Always eligible; no ticket/membership state to check
        _reverse_all_for_source_safe(
            conn, journal, "payment", payment_id, memo=f"Refund unfulfilled payment {payment_id}"
        )
        conn.execute(
            "UPDATE payments SET status = 'REFUNDED', fulfillment = 'RESOLVED_REFUNDED', refunded_at = ? WHERE id = ?;",
            (now, payment_id),
        )
    else:
        # FULFILLED: check with purpose handler
        handler = handlers.get(payment.purpose)
        if not handler:
            raise DomainError("VALIDATION", 422, f"No handler found for purpose {payment.purpose}")

        handler.check_refundable(conn, payment)  # may raise DomainError("REFUND_BLOCKED", 409)
        handler.apply_refund(conn, payment, now)

        _reverse_all_for_source_safe(
            conn, journal, "payment", payment_id, memo=f"Refund payment {payment_id}"
        )
        conn.execute(
            "UPDATE payments SET status = 'REFUNDED', refunded_at = ? WHERE id = ?;",
            (now, payment_id),
        )


def resolve_unfulfilled(
    conn: sqlite3.Connection,
    handlers: Handlers,
    payment_id: int,
    action: Literal["REFUND", "FULFILL"],
    actor_id: int,
    journal: Any = None,
) -> None:
    """Resolve an unfulfilled payment obligation per CONTRACT §3.1."""
    payment_row = conn.execute("SELECT * FROM payments WHERE id = ?;", (payment_id,)).fetchone()
    if not payment_row:
        raise DomainError("NOT_FOUND", 404, f"Payment {payment_id} not found")

    if payment_row["status"] != "SUCCEEDED" or payment_row["fulfillment"] != "UNFULFILLED":
        raise DomainError("VALIDATION", 422, "Payment is not an unfulfilled obligation")

    if action == "REFUND":
        refund_payment(conn, handlers, payment_id, actor_id, journal=journal)
        return

    if action == "FULFILL":
        open_term = conn.execute("SELECT id FROM terms WHERE status = 'OPEN';").fetchone()
        if not open_term or payment_row["term_id"] != open_term["id"]:
            raise DomainError(
                "VALIDATION", 422, "Can only manually fulfill payments created in the current OPEN term"
            )

        handler = handlers.get(payment_row["purpose"])
        if not handler:
            raise DomainError("VALIDATION", 422, f"No handler for purpose {payment_row['purpose']}")

        payment = Payment(
            id=payment_row["id"],
            public_id=payment_row["public_id"],
            user_id=payment_row["user_id"],
            purpose=payment_row["purpose"],
            ref_table=payment_row["ref_table"],
            ref_id=payment_row["ref_id"],
            amount_paise=payment_row["amount_paise"],
            status=payment_row["status"],
            fulfillment=payment_row["fulfillment"],
            term_id=payment_row["term_id"],
        )

        now = clock.now()
        res = handler.fulfill(conn, payment, manual=True, now=now)
        if res.outcome != "FULFILLED":
            code = res.reason if res.reason in {"SOLD_OUT", "INSUFFICIENT_STOCK", "ALREADY_MEMBER"} else "VALIDATION"
            raise DomainError(code, 409 if code != "VALIDATION" else 422, f"Fulfillment failed: {res.reason}")

        conn.execute(
            "UPDATE payments SET fulfillment = 'FULFILLED' WHERE id = ?;",
            (payment_id,),
        )
        _post_payment_late_fulfilled_safe(conn, journal, payment)
        return

    raise DomainError("VALIDATION", 422, f"Unknown action: {action}")


def resolve_receipt(
    conn: sqlite3.Connection,
    event_row_id: int,
    action: Literal["REFUND", "DISMISS"],
    actor_id: int,
    note: str,
    journal: Any = None,
) -> None:
    """Resolve an unapplied receipt event per CONTRACT §3.1."""
    row = conn.execute("SELECT * FROM payment_events WHERE id = ?;", (event_row_id,)).fetchone()
    if not row:
        raise DomainError("NOT_FOUND", 404, f"Event {event_row_id} not found")

    if row["outcome"] != "UNAPPLIED_RECEIPT":
        raise DomainError("VALIDATION", 422, "Event is not an unapplied receipt")

    if row["resolution"] is not None:
        raise DomainError("VALIDATION", 422, "Event is already resolved")

    if action == "DISMISS" and not note.strip():
        raise DomainError("VALIDATION", 422, "Dismissal requires an explanatory note")

    now = clock.now()
    _reverse_all_for_source_safe(
        conn, journal, "payment_event", event_row_id, memo=f"Resolve receipt ({action}): {note.strip()}"
    )

    conn.execute(
        """
        UPDATE payment_events
        SET resolution = ?, resolved_by = ?, resolved_at = ?, resolution_note = ?
        WHERE id = ?;
        """,
        (action, actor_id, now, note.strip(), event_row_id),
    )


def settle_payments(conn: sqlite3.Connection, as_of: str, journal: Any = None) -> int:
    """Settle all SUCCEEDED payments and UNAPPLIED_RECEIPT events >= 1 day old per CONTRACT §7, §14."""
    as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00")).astimezone(timezone.utc)
    cutoff_iso = (as_of_dt - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    count = 0

    # 1. Payments
    payments = conn.execute(
        """
        SELECT id, amount_paise FROM payments
        WHERE status = 'SUCCEEDED'
          AND settled_at IS NULL
          AND succeeded_at <= ?;
        """,
        (cutoff_iso,),
    ).fetchall()

    for p in payments:
        _post_settlement_safe(conn, journal, "payment", p["id"], p["amount_paise"])
        conn.execute("UPDATE payments SET settled_at = ? WHERE id = ?;", (as_of, p["id"]))
        count += 1

    # 2. Unapplied receipts (INR only)
    events = conn.execute(
        """
        SELECT id, amount_paise FROM payment_events
        WHERE outcome = 'UNAPPLIED_RECEIPT'
          AND resolution IS NULL
          AND settled_at IS NULL
          AND currency = 'INR'
          AND amount_paise > 0
          AND created_at <= ?;
        """,
        (cutoff_iso,),
    ).fetchall()

    for e in events:
        _post_settlement_safe(conn, journal, "payment_event", e["id"], e["amount_paise"])
        conn.execute("UPDATE payment_events SET settled_at = ? WHERE id = ?;", (as_of, e["id"]))
        count += 1

    return count


def expire_payments(conn: sqlite3.Connection, as_of: str) -> int:
    """Expire CREATED/PENDING payments created > 30 minutes ago per CONTRACT §3.1, §14."""
    as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00")).astimezone(timezone.utc)
    cutoff_iso = (as_of_dt - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Find affected payments
    expired_payments = conn.execute(
        """
        SELECT id, ref_table, ref_id FROM payments
        WHERE status IN ('CREATED', 'PENDING')
          AND created_at <= ?;
        """,
        (cutoff_iso,),
    ).fetchall()

    if not expired_payments:
        return 0

    for p in expired_payments:
        conn.execute("UPDATE payments SET status = 'EXPIRED' WHERE id = ?;", (p["id"],))
        # If membership, transition PENDING membership to CANCELLED per CONTRACT §3.2
        if p["ref_table"] == "memberships":
            conn.execute(
                "UPDATE memberships SET status = 'CANCELLED' WHERE id = ? AND status = 'PENDING';",
                (p["ref_id"],),
            )

    return len(expired_payments)
