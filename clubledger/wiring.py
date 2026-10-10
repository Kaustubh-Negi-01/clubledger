"""Explicit service and purpose-handler wiring per CONTRACT.md §13.2."""

from typing import Any

from clubledger.config import get_config
from clubledger.core import clock
from clubledger.core.errors import DomainError
from clubledger.core.types import (
    FulfillResult,
    Handlers,
    Payment,
    PurposeHandler,
    Services,
)
from clubledger.events import service as events_svc
from clubledger.membership import service as membership_svc


# --- MERCH Explicit Unavailable Handlers per prompt instructions ---


def _merch_unavailable_fulfill(conn: Any, payment: Payment, *, manual: bool, now: str) -> FulfillResult:
    return FulfillResult(outcome="UNFULFILLABLE", reason="STORE_SERVICE_UNAVAILABLE")


def _merch_unavailable_check_refundable(conn: Any, payment: Payment) -> None:
    raise DomainError("REFUND_BLOCKED", 409, "Store service unavailable")


def _merch_unavailable_apply_refund(conn: Any, payment: Payment, now: str) -> None:
    raise DomainError("REFUND_BLOCKED", 409, "Store service unavailable")


def build_handlers() -> Handlers:
    """Construct PurposeHandler mapping for DUES, TICKET, and MERCH without side-effects."""
    # 1. DUES handler (Owner B - genuine required dependency)
    dues_handler = PurposeHandler(
        purpose="DUES",
        fulfill=membership_svc.fulfill_dues,
        check_refundable=membership_svc.check_refundable_dues,
        apply_refund=membership_svc.apply_refund_dues,
    )

    # 2. TICKET handler (Owner B - genuine required dependency)
    ticket_handler = PurposeHandler(
        purpose="TICKET",
        fulfill=events_svc.fulfill_ticket_hold,
        check_refundable=events_svc.check_refundable_tickets,
        apply_refund=events_svc.apply_refund_tickets,
    )

    # 3. MERCH handler (Owner B - unimplemented MERCH remains clearly unavailable until B lands it)
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
    return Services(handlers=handlers, clock=clock, config=config)
