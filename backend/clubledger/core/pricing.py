# In plain English: Calculates eligible membership discounts using server-side data.
"""Pricing and entitlement rules per CONTRACT.md §2 and §13.3."""

import sqlite3
from typing import Literal

from clubledger.core.errors import DomainError
from clubledger.core.types import Membership


def active_membership(
    conn: sqlite3.Connection, user_id: int, at: str
) -> Membership | None:
    """Resolve active membership covering instant 'at' per CONTRACT §2.

    Returns Membership if user has status='ACTIVE' with starts_at <= at < expires_at
    and user account is active, else None.
    """
    # Guard against queries before memberships table exists
    has_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memberships';"
    ).fetchone()
    if not has_table:
        return None

    row = conn.execute(
        """
        SELECT m.id, m.user_id, m.plan_id, m.membership_year, m.status,
               m.starts_at, m.expires_at, m.member_code, m.qr_token, m.payment_id
        FROM memberships m
        JOIN users u ON m.user_id = u.id
        WHERE m.user_id = ?
          AND u.is_active = 1
          AND m.status = 'ACTIVE'
          AND m.starts_at <= ?
          AND m.expires_at > ?
        ORDER BY m.expires_at DESC
        LIMIT 1;
        """,
        (user_id, at, at),
    ).fetchone()

    if not row:
        return None

    return Membership(
        id=row["id"],
        user_id=row["user_id"],
        plan_id=row["plan_id"],
        membership_year=row["membership_year"],
        status=row["status"],
        starts_at=row["starts_at"],
        expires_at=row["expires_at"],
        member_code=row["member_code"],
        qr_token=row["qr_token"],
        payment_id=row["payment_id"],
    )


def ticket_price(
    conn: sqlite3.Connection, event_id: int, user_id: int, at: str
) -> tuple[int, Literal["MEMBER", "PUBLIC"]]:
    """Calculate server-authoritative ticket price per CONTRACT §2.

    Returns (price_paise, tier) where tier is 'MEMBER' or 'PUBLIC'.
    Member price is min(event.member_price_paise, public_price * (10000 - discount_bps) // 10000).
    """
    has_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='events';"
    ).fetchone()
    if not has_table:
        raise DomainError("NOT_FOUND", 404, "Events table not found")

    event = conn.execute(
        "SELECT member_price_paise, public_price_paise FROM events WHERE id = ?;",
        (event_id,),
    ).fetchone()
    if not event:
        raise DomainError("NOT_FOUND", 404, f"Event {event_id} not found")

    public_paise: int = event["public_price_paise"]
    event_member_paise: int = event["member_price_paise"]

    mem = active_membership(conn, user_id, at)
    if mem is None:
        return public_paise, "PUBLIC"

    # Member is active; check plan ticket_discount_bps
    plan = conn.execute(
        "SELECT ticket_discount_bps FROM membership_plans WHERE id = ?;",
        (mem.plan_id,),
    ).fetchone()
    discount_bps: int = plan["ticket_discount_bps"] if plan else 0

    plan_discounted = (public_paise * (10000 - discount_bps)) // 10000
    final_price = min(event_member_paise, plan_discounted)
    return final_price, "MEMBER"


def merch_price(
    conn: sqlite3.Connection, base_paise: int, user_id: int, at: str
) -> tuple[int, Literal["MEMBER", "PUBLIC"]]:
    """Calculate server-authoritative merchandise unit price per CONTRACT §2.

    Member price is floor(base_paise * (10000 - discount_bps) // 10000).
    """
    mem = active_membership(conn, user_id, at)
    if mem is None:
        return base_paise, "PUBLIC"

    plan = conn.execute(
        "SELECT merch_discount_bps FROM membership_plans WHERE id = ?;",
        (mem.plan_id,),
    ).fetchone()
    discount_bps: int = plan["merch_discount_bps"] if plan else 0

    discounted = (base_paise * (10000 - discount_bps)) // 10000
    return discounted, "MEMBER"
