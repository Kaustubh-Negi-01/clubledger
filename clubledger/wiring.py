"""Explicit service and purpose-handler wiring per CONTRACT.md §13.2."""

from dataclasses import dataclass
from typing import Any

from clubledger.config import get_config
from clubledger.core.errors import DomainError
from clubledger.core.types import (
    FulfillResult,
    Handlers,
    Payment,
    PurposeHandler,
)


@dataclass(frozen=True)
class Services:
    handlers: Handlers
    config: Any


# --- DUES Fallbacks when B's membership module is not yet published ---


def _default_fulfill_dues(conn: Any, payment: Payment, *, manual: bool, now: str) -> FulfillResult:
    return FulfillResult(outcome="UNFULFILLABLE", reason="MEMBERSHIP_SERVICE_UNAVAILABLE")


def _default_check_refundable_dues(conn: Any, payment: Payment) -> None:
    raise DomainError("REFUND_BLOCKED", 409, "Membership refund check unavailable")


def _default_apply_refund_dues(conn: Any, payment: Payment, now: str) -> None:
    raise DomainError("REFUND_BLOCKED", 409, "Membership refund apply unavailable")


# --- TICKET Fallbacks when B's events module is not yet published ---


def _default_fulfill_tickets(conn: Any, payment: Payment, *, manual: bool, now: str) -> FulfillResult:
    return FulfillResult(outcome="UNFULFILLABLE", reason="EVENTS_SERVICE_UNAVAILABLE")


def _default_check_refundable_tickets(conn: Any, payment: Payment) -> None:
    raise DomainError("REFUND_BLOCKED", 409, "Events refund check unavailable")


def _default_apply_refund_tickets(conn: Any, payment: Payment, now: str) -> None:
    raise DomainError("REFUND_BLOCKED", 409, "Events refund apply unavailable")


# --- MERCH Explicit Unavailable Handlers per prompt instructions ---


def _merch_unavailable_fulfill(conn: Any, payment: Payment, *, manual: bool, now: str) -> FulfillResult:
    return FulfillResult(outcome="UNFULFILLABLE", reason="STORE_SERVICE_UNAVAILABLE")


def _merch_unavailable_check_refundable(conn: Any, payment: Payment) -> None:
    raise DomainError("REFUND_BLOCKED", 409, "Store service unavailable")


def _merch_unavailable_apply_refund(conn: Any, payment: Payment, now: str) -> None:
    raise DomainError("REFUND_BLOCKED", 409, "Store service unavailable")


def build_handlers() -> Handlers:
    """Construct PurposeHandler mapping for DUES, TICKET, and MERCH without side-effects."""
    # 1. DUES handler (Owner B)
    try:
        from clubledger.membership import service as membership_svc

        fulfill_dues = getattr(membership_svc, "fulfill_dues", _default_fulfill_dues)
        check_refundable_dues = getattr(
            membership_svc, "check_refundable_dues", _default_check_refundable_dues
        )
        apply_refund_dues = getattr(membership_svc, "apply_refund_dues", _default_apply_refund_dues)
    except ImportError:
        fulfill_dues = _default_fulfill_dues
        check_refundable_dues = _default_check_refundable_dues
        apply_refund_dues = _default_apply_refund_dues

    dues_handler = PurposeHandler(
        purpose="DUES",
        fulfill=fulfill_dues,
        check_refundable=check_refundable_dues,
        apply_refund=apply_refund_dues,
    )

    # 2. TICKET handler (Owner B)
    try:
        from clubledger.events import service as events_svc

        fulfill_tickets = getattr(events_svc, "fulfill_ticket_hold", _default_fulfill_tickets)
        check_refundable_tickets = getattr(
            events_svc, "check_refundable_tickets", _default_check_refundable_tickets
        )
        apply_refund_tickets = getattr(
            events_svc, "apply_refund_tickets", _default_apply_refund_tickets
        )
    except ImportError:
        fulfill_tickets = _default_fulfill_tickets
        check_refundable_tickets = _default_check_refundable_tickets
        apply_refund_tickets = _default_apply_refund_tickets

    ticket_handler = PurposeHandler(
        purpose="TICKET",
        fulfill=fulfill_tickets,
        check_refundable=check_refundable_tickets,
        apply_refund=apply_refund_tickets,
    )

    # 3. MERCH handler (Owner B)
    try:
        from clubledger.store import service as store_svc

        fulfill_merch = getattr(store_svc, "fulfill_merch_order", _merch_unavailable_fulfill)
        check_refundable_merch = getattr(
            store_svc, "check_refundable_merch", _merch_unavailable_check_refundable
        )
        apply_refund_merch = getattr(store_svc, "apply_refund_merch", _merch_unavailable_apply_refund)
    except ImportError:
        fulfill_merch = _merch_unavailable_fulfill
        check_refundable_merch = _merch_unavailable_check_refundable
        apply_refund_merch = _merch_unavailable_apply_refund

    merch_handler = PurposeHandler(
        purpose="MERCH",
        fulfill=fulfill_merch,
        check_refundable=check_refundable_merch,
        apply_refund=apply_refund_merch,
    )

    return {
        "DUES": dues_handler,
        "TICKET": ticket_handler,
        "MERCH": merch_handler,
    }


def build_services() -> Services:
    """Build Services container per CONTRACT §13.2."""
    config = get_config()
    handlers = build_handlers()
    return Services(handlers=handlers, config=config)
