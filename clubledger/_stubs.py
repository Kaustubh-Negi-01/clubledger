"""Stub signatures per CONTRACT.md §13.3 raising NotImplementedError."""

import sqlite3
from typing import Any, Literal

from clubledger.core.types import (
    CancelSummary,
    CartItem,
    CashSummary,
    CheckInResult,
    DrillDown,
    EventOutcome,
    EventReport,
    FulfillResult,
    Handlers,
    IncomeExpense,
    MemberCheck,
    Membership,
    MerchOrder,
    Movement,
    Payment,
    Session,
    Subscriber,
    TicketHold,
)


# core/auth.py (A)
def create_session(conn: sqlite3.Connection, user_id: int) -> tuple[str, str]:
    raise NotImplementedError


def load_session(conn: sqlite3.Connection, raw_token: str) -> Session | None:
    raise NotImplementedError


def revoke_session(conn: sqlite3.Connection, session_id: int) -> None:
    raise NotImplementedError


def require_perm(code: str) -> Any:
    raise NotImplementedError


def verify_csrf(session: Session, supplied: str) -> None:
    raise NotImplementedError


# core/pricing.py (A)
def active_membership(conn: sqlite3.Connection, user_id: int, at: str) -> Membership | None:
    raise NotImplementedError


def ticket_price(conn: sqlite3.Connection, event_id: int, user_id: int, at: str) -> tuple[int, Literal["MEMBER", "PUBLIC"]]:
    raise NotImplementedError


def merch_price(conn: sqlite3.Connection, base_paise: int, user_id: int, at: str) -> tuple[int, Literal["MEMBER", "PUBLIC"]]:
    raise NotImplementedError


# payments/service.py (A)
def create_payment(conn: sqlite3.Connection, *, user_id: int, purpose: str, ref_table: str, ref_id: int, amount_paise: int) -> Payment:
    raise NotImplementedError


def handle_event(conn: sqlite3.Connection, handlers: Handlers, raw_body: bytes, signature_header: str, now: str) -> EventOutcome:
    raise NotImplementedError


def refund_payment(conn: sqlite3.Connection, handlers: Handlers, payment_id: int, actor_id: int) -> None:
    raise NotImplementedError


def resolve_unfulfilled(conn: sqlite3.Connection, handlers: Handlers, payment_id: int, action: Literal["REFUND", "FULFILL"], actor_id: int) -> None:
    raise NotImplementedError


def resolve_receipt(conn: sqlite3.Connection, event_row_id: int, action: Literal["REFUND", "DISMISS"], actor_id: int, note: str) -> None:
    raise NotImplementedError


def settle_payments(conn: sqlite3.Connection, as_of: str) -> int:
    raise NotImplementedError


def expire_payments(conn: sqlite3.Connection, as_of: str) -> int:
    raise NotImplementedError


# membership/service.py (B)
def start_join(conn: sqlite3.Connection, user_id: int, plan_id: int, idempotency_key: str) -> Payment:
    raise NotImplementedError


def fulfill_dues(conn: sqlite3.Connection, payment: Payment, *, manual: bool, now: str) -> FulfillResult:
    raise NotImplementedError


def check_refundable_dues(conn: sqlite3.Connection, payment: Payment) -> None:
    raise NotImplementedError


def apply_refund_dues(conn: sqlite3.Connection, payment: Payment, now: str) -> None:
    raise NotImplementedError


def lookup_member(conn: sqlite3.Connection, *, code: str | None = None, qr_token: str | None = None, at: str) -> MemberCheck:
    raise NotImplementedError


def enqueue_renewal_reminders(conn: sqlite3.Connection, as_of: str) -> int:
    raise NotImplementedError


# events/service.py (B)
def create_hold(conn: sqlite3.Connection, user_id: int, event_id: int, qty: int, idempotency_key: str) -> tuple[TicketHold, Payment | None]:
    raise NotImplementedError


def fulfill_ticket_hold(conn: sqlite3.Connection, payment: Payment, *, manual: bool, now: str) -> FulfillResult:
    raise NotImplementedError


def check_refundable_tickets(conn: sqlite3.Connection, payment: Payment) -> None:
    raise NotImplementedError


def apply_refund_tickets(conn: sqlite3.Connection, payment: Payment, now: str) -> None:
    raise NotImplementedError


def expire_holds(conn: sqlite3.Connection, as_of: str) -> int:
    raise NotImplementedError


def check_in(conn: sqlite3.Connection, event_id: int, code: str, staff_id: int) -> CheckInResult:
    raise NotImplementedError


def cancel_event(conn: sqlite3.Connection, handlers: Handlers, event_id: int, actor_id: int) -> CancelSummary:
    raise NotImplementedError


def event_report(conn: sqlite3.Connection, event_id: int) -> EventReport:
    raise NotImplementedError


# store/service.py (B)
def reserve_cart(conn: sqlite3.Connection, user_id: int, items: list[CartItem], idempotency_key: str) -> tuple[MerchOrder, Payment]:
    raise NotImplementedError


def fulfill_merch_order(conn: sqlite3.Connection, payment: Payment, *, manual: bool, now: str) -> FulfillResult:
    raise NotImplementedError


def check_refundable_merch(conn: sqlite3.Connection, payment: Payment) -> None:
    raise NotImplementedError


def apply_refund_merch(conn: sqlite3.Connection, payment: Payment, now: str) -> None:
    raise NotImplementedError


def expire_orders(conn: sqlite3.Connection, as_of: str) -> int:
    raise NotImplementedError


def mark_picked_up(conn: sqlite3.Connection, order_id: int, staff_id: int) -> None:
    raise NotImplementedError


# journal/service.py (C)
def post_entry(conn: sqlite3.Connection, *, term_id: int, entry_date: str, source_type: str, source_id: int, source_event: str, memo: str | None, lines: list[Any], reverses_entry_id: int | None = None, adjusts_term_id: int | None = None) -> int:
    raise NotImplementedError


def reverse_entry(conn: sqlite3.Connection, entry_id: int, memo: str) -> int:
    raise NotImplementedError


def reverse_all_for_source(conn: sqlite3.Connection, source_type: str, source_id: int, memo: str) -> list[int]:
    raise NotImplementedError


def post_payment_received(conn: sqlite3.Connection, payment: Payment, *, fulfilled: bool) -> int:
    raise NotImplementedError


def post_payment_late_fulfilled(conn: sqlite3.Connection, payment: Payment) -> int:
    raise NotImplementedError


def post_receipt_event(conn: sqlite3.Connection, event_row: Any) -> int | None:
    raise NotImplementedError


def post_settlement(conn: sqlite3.Connection, source_type: str, source_id: int, amount_paise: int) -> int:
    raise NotImplementedError


def post_expense_approved(conn: sqlite3.Connection, expense: Any) -> int:
    raise NotImplementedError


def post_expense_paid(conn: sqlite3.Connection, expense: Any) -> int:
    raise NotImplementedError


# reports/service.py (C)
def balance(conn: sqlite3.Connection, account_code: str, *, at: str | None = None, watermark_id: int | None = None) -> int:
    raise NotImplementedError


def movement(conn: sqlite3.Connection, account_code: str, term_id: int) -> Movement:
    raise NotImplementedError


def cash_summary(conn: sqlite3.Connection, term_id: int, *, at: str | None = None) -> CashSummary:
    raise NotImplementedError


def income_expense(conn: sqlite3.Connection, term_id: int) -> IncomeExpense:
    raise NotImplementedError


def drilldown(conn: sqlite3.Connection, *, account_code: str | None = None, entry_id: int | None = None, term_id: int | None = None, at: str | None = None, watermark_id: int | None = None) -> DrillDown:
    raise NotImplementedError


# comms (C)
def publish_announcement(conn: sqlite3.Connection, announcement_id: int, actor_id: int) -> int:
    raise NotImplementedError


def subscribe(conn: sqlite3.Connection, email: str, user_id: int | None = None) -> Subscriber:
    raise NotImplementedError


def unsubscribe(conn: sqlite3.Connection, token: str) -> None:
    raise NotImplementedError


def process_mail_outbox(conn: sqlite3.Connection, limit: int = 100) -> int:
    raise NotImplementedError


# close/service.py, handover/service.py (C)
def run_close(conn: sqlite3.Connection, term_id: int, actor_id: int) -> int:
    raise NotImplementedError


def post_adjustment(conn: sqlite3.Connection, actor_id: int, adjusts_term_id: int, memo: str, lines: list[Any]) -> int:
    raise NotImplementedError


def run_handover(conn: sqlite3.Connection, term_id: int, from_user_id: int, to_user_id: int, role_codes: list[str], notes: str) -> int:
    raise NotImplementedError
