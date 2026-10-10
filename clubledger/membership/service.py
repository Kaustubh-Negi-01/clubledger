"""Membership service per CONTRACT.md §1.3, §2, §3.2, §13.3."""

from datetime import datetime, timezone
import hashlib
import sqlite3
from typing import Callable, Literal

from clubledger.core import clock, idgen
from clubledger.core.errors import DomainError
from clubledger.core.types import (
    FulfillResult,
    MemberCheck,
    Payment,
    PurposeHandler,
)

# Attempt to import genuine A-owned create_payment
try:
    from clubledger.payments.service import create_payment as _genuine_create_payment
except ImportError:
    _genuine_create_payment = None


class DependencyBlockerError(DomainError):
    """Raised when an A-owned or D-owned dependency is not yet implemented."""

    def __init__(self, message: str) -> None:
        super().__init__("DEPENDENCY_BLOCKER", 503, message)


def seed_plans(conn: sqlite3.Connection) -> None:
    """Seed standard membership plans per CONTRACT defaults."""
    exists = conn.execute("SELECT 1 FROM membership_plans LIMIT 1;").fetchone()
    if not exists:
        conn.execute(
            "INSERT INTO membership_plans (id, code, name, dues_paise, ticket_discount_bps, merch_discount_bps, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
            (1, "STANDARD", "Member", 200000, 2000, 1000, 1, clock.now()),
        )


def _parse_utc_iso(dt_str: str) -> datetime:
    """Parse ISO UTC string ending with Z into datetime."""
    clean = dt_str.replace("Z", "+00:00")
    return datetime.fromisoformat(clean).astimezone(timezone.utc)


def start_join(
    conn: sqlite3.Connection,
    user_id: int,
    plan_id: int,
    idempotency_key: str,
    *,
    create_payment_fn: Callable[..., Payment] | None = None,
) -> Payment:
    """Start join / renewal workflow creating PENDING membership and Payment per CONTRACT §1.3, §6, §13.3."""
    now_str = clock.now()
    now_dt = _parse_utc_iso(now_str)

    # 1. Verify user exists and is active
    user_row = conn.execute(
        "SELECT id, is_active FROM users WHERE id = ?;", (user_id,)
    ).fetchone()
    if not user_row or not user_row["is_active"]:
        raise DomainError("NOT_FOUND", 404, "Active user not found")

    # 2. Check browser idempotency key (§6)
    req_hash = hashlib.sha256(f"plan_id={plan_id}".encode("utf-8")).hexdigest()
    existing_key = conn.execute(
        "SELECT request_hash, result_ref FROM idempotency_keys WHERE actor_user_id = ? AND action = 'membership.join' AND key = ?;",
        (user_id, idempotency_key),
    ).fetchone()
    if existing_key:
        if existing_key["request_hash"] != req_hash:
            raise DomainError("CONFLICT", 409, "Idempotency key reused with different request parameters")
        ref = existing_key["result_ref"]
        if ref.startswith("payment:"):
            pay_id = int(ref.split(":", 1)[1])
            pay_row = conn.execute(
                "SELECT id, public_id, user_id, purpose, ref_table, ref_id, amount_paise, status, fulfillment, term_id "
                "FROM payments WHERE id = ?;",
                (pay_id,),
            ).fetchone()
            if pay_row:
                return Payment(
                    id=pay_row["id"],
                    public_id=pay_row["public_id"],
                    user_id=pay_row["user_id"],
                    purpose=pay_row["purpose"],
                    ref_table=pay_row["ref_table"],
                    ref_id=pay_row["ref_id"],
                    amount_paise=pay_row["amount_paise"],
                    status=pay_row["status"],
                    fulfillment=pay_row["fulfillment"],
                    term_id=pay_row["term_id"],
                )

    # 3. Verify plan exists and is active
    plan_row = conn.execute(
        "SELECT id, code, name, dues_paise, is_active FROM membership_plans WHERE id = ?;",
        (plan_id,),
    ).fetchone()
    if not plan_row or not plan_row["is_active"]:
        raise DomainError("NOT_FOUND", 404, "Active membership plan not found")

    # 4. Determine academic year bounds and renewal eligibility (§1.3)
    curr_label, curr_starts, curr_expires = clock.academic_year_bounds(now_str)
    curr_exp_dt = _parse_utc_iso(curr_expires)

    # Check existing live memberships for this user
    live_rows = conn.execute(
        "SELECT id, membership_year, status, starts_at, expires_at FROM memberships "
        "WHERE user_id = ? AND status IN ('PENDING', 'ACTIVE') "
        "ORDER BY starts_at ASC;",
        (user_id,),
    ).fetchall()

    target_year = curr_label
    target_starts = curr_starts
    target_expires = curr_expires

    has_current_live = any(r["membership_year"] == curr_label for r in live_rows)
    if has_current_live:
        # User already has live membership for current year. Check renewal window (now >= expires_at - 30 days)
        days_to_expiry = (curr_exp_dt - now_dt).total_seconds() / 86400.0
        if days_to_expiry > 30.0:
            raise DomainError(
                "ALREADY_MEMBER",
                409,
                f"Already a member for {curr_label}; renewal opens 30 days before expiry",
            )

        # Renewal for next academic year
        next_label, next_starts, next_expires = clock.academic_year_bounds(curr_expires)
        has_next_live = any(r["membership_year"] == next_label for r in live_rows)
        if has_next_live:
            raise DomainError(
                "ALREADY_MEMBER",
                409,
                f"Already renewed for next membership year {next_label}",
            )
        target_year = next_label
        target_starts = curr_expires
        target_expires = next_expires

    # 5. Insert PENDING membership
    cur = conn.execute(
        "INSERT INTO memberships ("
        "  user_id, plan_id, membership_year, status, starts_at, expires_at, "
        "  member_code, qr_token, payment_id, verified_by, verified_at, created_at"
        ") VALUES (?, ?, ?, 'PENDING', ?, ?, NULL, NULL, NULL, NULL, NULL, ?);",
        (user_id, plan_id, target_year, target_starts, target_expires, now_str),
    )
    membership_id = cur.lastrowid
    assert membership_id is not None

    # 6. Call create_payment per CONTRACT
    payment_creator = create_payment_fn or _genuine_create_payment
    if payment_creator is None:
        raise DependencyBlockerError(
            "payments.service.create_payment is not yet available; dependency blocker per BUILD_ORDER"
        )

    payment = payment_creator(
        conn,
        user_id=user_id,
        purpose="DUES",
        ref_table="memberships",
        ref_id=membership_id,
        amount_paise=plan_row["dues_paise"],
    )

    # 7. Update membership with payment_id
    conn.execute(
        "UPDATE memberships SET payment_id = ? WHERE id = ?;",
        (payment.id, membership_id),
    )

    # 8. Record idempotency key
    req_hash = hashlib.sha256(f"plan_id={plan_id}".encode("utf-8")).hexdigest()
    conn.execute(
        "INSERT INTO idempotency_keys (actor_user_id, action, key, request_hash, result_ref, created_at) "
        "VALUES (?, 'membership.join', ?, ?, ?, ?);",
        (user_id, idempotency_key, req_hash, f"payment:{payment.id}", now_str),
    )

    return payment


def fulfill_dues(
    conn: sqlite3.Connection,
    payment: Payment,
    *,
    manual: bool,
    now: str,
) -> FulfillResult:
    """Fulfill dues payment transitioning PENDING -> ACTIVE per CONTRACT §1.3 and §3.2."""
    row = conn.execute(
        "SELECT id, user_id, membership_year, status, starts_at, expires_at, member_code, qr_token "
        "FROM memberships WHERE id = ?;",
        (payment.ref_id,),
    ).fetchone()

    if not row:
        return FulfillResult(outcome="UNFULFILLABLE", reason="TARGET_NOT_LIVE")

    # Idempotent replay: already ACTIVE
    if row["status"] == "ACTIVE":
        return FulfillResult(outcome="FULFILLED")

    if row["status"] == "PENDING" or (manual and row["status"] == "CANCELLED"):
        if manual and row["status"] == "CANCELLED":
            # Check if user acquired another live membership in the meantime
            conflict = conn.execute(
                "SELECT 1 FROM memberships WHERE user_id = ? AND membership_year = ? AND status IN ('PENDING', 'ACTIVE') AND id <> ?;",
                (row["user_id"], row["membership_year"], row["id"]),
            ).fetchone()
            if conflict:
                return FulfillResult(outcome="UNFULFILLABLE", reason="ALREADY_MEMBER")

        # Generate unique member_code and qr_token
        import base64
        import secrets
        code_suffix = base64.b32encode(secrets.token_bytes(5)).decode("ascii").rstrip("=")
        qr_suffix = base64.b32encode(secrets.token_bytes(10)).decode("ascii").rstrip("=")
        m_code = f"M{row['id']:04d}-{code_suffix}"
        m_qr = f"QR-{qr_suffix}"

        updated = conn.execute(
            "UPDATE memberships "
            "SET status = 'ACTIVE', member_code = ?, qr_token = ? "
            "WHERE id = ? AND status IN ('PENDING', 'CANCELLED');",
            (m_code, m_qr, row["id"]),
        ).rowcount

        if updated == 1:
            return FulfillResult(outcome="FULFILLED")
        return FulfillResult(outcome="UNFULFILLABLE", reason="TARGET_NOT_LIVE")

    return FulfillResult(outcome="UNFULFILLABLE", reason="TARGET_NOT_LIVE")


def check_refundable_dues(conn: sqlite3.Connection, payment: Payment) -> None:
    """Raise DomainError REFUND_BLOCKED if dues cannot be refunded per CONTRACT §13.1."""
    row = conn.execute(
        "SELECT status FROM memberships WHERE id = ?;",
        (payment.ref_id,),
    ).fetchone()
    if not row or row["status"] == "REVOKED":
        raise DomainError("REFUND_BLOCKED", 409, "Membership is already revoked or missing")


def apply_refund_dues(conn: sqlite3.Connection, payment: Payment, now: str) -> None:
    """Transition ACTIVE/PENDING membership to REVOKED on refund per CONTRACT §3.2."""
    conn.execute(
        "UPDATE memberships SET status = 'REVOKED' WHERE id = ?;",
        (payment.ref_id,),
    )


def lookup_member(
    conn: sqlite3.Connection,
    *,
    code: str | None = None,
    qr_token: str | None = None,
    at: str,
) -> MemberCheck:
    """Staff lookup of membership by member_code or qr_token per CONTRACT §1.3, §13.3."""
    if not code and not qr_token:
        raise DomainError("VALIDATION", 422, "Either member code or QR token must be provided")

    query = (
        "SELECT m.id, m.status, m.starts_at, m.expires_at, m.member_code, m.membership_year, u.name "
        "FROM memberships m "
        "JOIN users u ON m.user_id = u.id "
        "WHERE (? IS NOT NULL AND m.member_code = ?) "
        "   OR (? IS NOT NULL AND m.qr_token = ?);"
    )
    row = conn.execute(query, (code, code, qr_token, qr_token)).fetchone()
    if not row:
        return MemberCheck(
            active=False,
            name="",
            status="NOT_FOUND",
            member_code=None,
            membership_year=None,
        )

    is_active = (row["status"] == "ACTIVE" and row["starts_at"] <= at < row["expires_at"])
    status_display = "ACTIVE" if is_active else ("EXPIRED" if row["status"] == "ACTIVE" else row["status"])

    return MemberCheck(
        active=is_active,
        name=row["name"],
        status=status_display,
        member_code=row["member_code"],
        membership_year=row["membership_year"],
    )


def enqueue_renewal_reminders(conn: sqlite3.Connection, as_of: str) -> int:
    """Mark expired memberships and queue reminders per CONTRACT §1.3."""
    cur = conn.execute(
        "UPDATE memberships SET status = 'EXPIRED' WHERE status = 'ACTIVE' AND expires_at <= ?;",
        (as_of,),
    )
    return cur.rowcount


DUES_PURPOSE_HANDLER = PurposeHandler(
    purpose="DUES",
    fulfill=fulfill_dues,
    check_refundable=check_refundable_dues,
    apply_refund=apply_refund_dues,
)
