"""Shared types and protocols per CONTRACT.md §13.1 and §13.3."""

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Protocol


# --- §13.1 Types ---


@dataclass(frozen=True)
class Payment:
    id: int
    public_id: str
    user_id: int
    purpose: str
    ref_table: str
    ref_id: int
    amount_paise: int
    status: str
    fulfillment: str
    term_id: int


@dataclass(frozen=True)
class FulfillResult:
    outcome: Literal["FULFILLED", "UNFULFILLABLE"]
    reason: str | None = None  # required when UNFULFILLABLE: 'TARGET_NOT_LIVE','SOLD_OUT','INSUFFICIENT_STOCK','ALREADY_MEMBER'


@dataclass(frozen=True)
class EventOutcome:
    event_row_id: int
    outcome: str
    reason: str | None
    payment_id: int | None
    http_status: int


@dataclass(frozen=True)
class Line:
    account_code: str
    debit_paise: int = 0
    credit_paise: int = 0


class Fulfiller(Protocol):
    def __call__(self, conn: Any, payment: Payment, *, manual: bool, now: str) -> FulfillResult: ...


class RefundCheck(Protocol):
    def __call__(self, conn: Any, payment: Payment) -> None: ...  # raises DomainError REFUND_BLOCKED


class RefundApply(Protocol):
    def __call__(self, conn: Any, payment: Payment, now: str) -> None: ...


@dataclass(frozen=True)
class PurposeHandler:
    purpose: str
    fulfill: Fulfiller
    check_refundable: RefundCheck
    apply_refund: RefundApply


Handlers = Mapping[str, PurposeHandler]  # keys 'DUES','TICKET','MERCH'


# --- Additional shared domain types referenced across boundaries (§13.2, §13.3) ---


@dataclass(frozen=True)
class Session:
    id: int
    user_id: int
    csrf_token: str
    last_seen_at: str
    idle_expires_at: str
    absolute_expires_at: str
    revoked_at: str | None = None


@dataclass(frozen=True)
class Membership:
    id: int
    user_id: int
    plan_id: int
    membership_year: str
    status: str
    starts_at: str
    expires_at: str
    member_code: str | None = None
    qr_token: str | None = None
    payment_id: int | None = None


@dataclass(frozen=True)
class MemberCheck:
    active: bool
    name: str
    status: str
    member_code: str | None = None
    membership_year: str | None = None


@dataclass(frozen=True)
class TicketHold:
    id: int
    event_id: int
    user_id: int
    qty: int
    unit_price_paise: int
    price_tier: Literal["MEMBER", "PUBLIC"]
    status: str
    expires_at: str
    created_at: str


@dataclass(frozen=True)
class Ticket:
    id: int
    event_id: int
    hold_id: int
    seat_index: int
    user_id: int
    payment_id: int | None
    code: str
    price_paise: int
    price_tier: Literal["MEMBER", "PUBLIC"]
    status: str
    used_at: str | None = None
    used_by: int | None = None


@dataclass(frozen=True)
class CartItem:
    variant_id: int
    qty: int


@dataclass(frozen=True)
class MerchOrder:
    id: int
    user_id: int
    status: str
    expires_at: str
    total_paise: int
    price_tier: Literal["MEMBER", "PUBLIC"]
    payment_id: int | None
    created_at: str


@dataclass(frozen=True)
class CheckInResult:
    status: Literal["OK", "ALREADY_USED", "REJECTED"]
    message: str
    ticket_id: int | None = None


@dataclass(frozen=True)
class CancelSummary:
    event_id: int
    refunded_count: int
    void_count: int
    flagged_count: int


@dataclass(frozen=True)
class EventReport:
    event_id: int
    sold: int
    attended: int
    no_shows: int
    gross: int
    refunded: int
    net_proceeds: int


@dataclass(frozen=True)
class Movement:
    debit_paise: int
    credit_paise: int


@dataclass(frozen=True)
class CashSummary:
    cash_on_hand: int
    in_clearing: int
    unfulfilled_obligations: int
    reimbursements_payable: int


@dataclass(frozen=True)
class IncomeExpense:
    term_id: int
    net_surplus: int
    accounts: Mapping[str, int]


@dataclass(frozen=True)
class DrillDown:
    title: str
    total_paise: int
    items: list[dict[str, Any]]


@dataclass(frozen=True)
class Subscriber:
    id: int
    email: str
    status: str
    unsub_token: str


@dataclass(frozen=True)
class Services:
    handlers: Handlers
    clock: Any
    config: Any
