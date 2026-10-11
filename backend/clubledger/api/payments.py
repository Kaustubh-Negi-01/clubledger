# In plain English: Serves checkout and handles simulator outcomes, verified callbacks and officer payment actions.
"""HTTP endpoints for payments, simulator, webhooks, and payment admin per CONTRACT.md §12."""

from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Form, Header, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.templating import Jinja2Templates

from clubledger.config import get_db_path, get_sim_secret
from clubledger.core import clock
from clubledger.security.auth import get_current_session, require_perm
from clubledger.security.csrf import verify_csrf_token
from clubledger.core.db import connect, unit_of_work
from clubledger.core.errors import DomainError
from clubledger.core.types import Handlers, Payment, Session
from clubledger.payments.service import (
    handle_event,
    refund_payment,
    resolve_receipt,
    resolve_unfulfilled,
)
from clubledger.payments.simulator import dispatch_simulated_outcome
from clubledger.payments.webhook import verify_webhook_request
from clubledger.wiring import build_handlers

router = APIRouter()

from clubledger.paths import TEMPLATES_DIR
from clubledger.presentation.event_display import event_date, event_time

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _get_client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def get_handlers() -> Handlers:
    return build_handlers()


# --- 1. Simulator Browser Pages ---


@router.get("/pay/{public_id}", response_class=HTMLResponse)
def get_pay(
    request: Request,
    public_id: str,
    session: Session = Depends(get_current_session),
) -> Response:
    """Render simulated payment checkout page per CONTRACT §5, §12."""
    conn = connect(get_db_path())
    try:
        # Enforce ownership: must match user_id. Foreign IDs return 404 (CONTRACT §4.2)
        row = conn.execute(
            "SELECT * FROM payments WHERE public_id = ? AND user_id = ?;",
            (public_id, session.user_id),
        ).fetchone()
        if not row:
            raise DomainError("NOT_FOUND", 404, "Payment not found")

        # CREATED transitions to PENDING when simulator page is opened per CONTRACT §3.1
        if row["status"] == "CREATED":
            conn.execute(
                "UPDATE payments SET status = 'PENDING' WHERE id = ?;", (row["id"],)
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM payments WHERE id = ?;", (row["id"],)
            ).fetchone()

        # Optional display details come from this user's actual ticket reservation.
        # The saved payment remains the authoritative amount and status.
        ticket_event = None
        if row["purpose"] == "TICKET" and row["ref_table"] == "ticket_holds":
            event_row = conn.execute(
                "SELECT e.title, e.venue, e.starts_at, h.qty "
                "FROM ticket_holds h JOIN events e ON e.id = h.event_id "
                "WHERE h.id = ? AND h.user_id = ?",
                (row["ref_id"], session.user_id),
            ).fetchone()
            if event_row:
                ticket_event = dict(event_row)
                ticket_event["display_date"] = event_date(event_row["starts_at"])
                ticket_event["display_time"] = event_time(event_row["starts_at"])

        payment_dict = dict(row)
        return templates.TemplateResponse(
            request=request,
            name="payments/pay.html",
            context={
                "payment": payment_dict,
                "ticket_event": ticket_event,
                "csrf_token": session.csrf_token,
                "show_result": request.query_params.get("result") == "1"
                and row["status"] not in {"CREATED", "PENDING"},
            },
        )
    finally:
        conn.close()


@router.post("/pay/{public_id}/outcome")
async def post_pay_outcome(
    request: Request,
    public_id: str,
    outcome: Annotated[str, Form()],
    csrf_token: Annotated[str | None, Form()] = None,
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    session: Session = Depends(get_current_session),
    handlers: Handlers = Depends(get_handlers),
) -> Response:
    """Simulate payment outcome (server-side signed) per CONTRACT §5."""
    token_to_verify = csrf_token or x_csrf_token
    verify_csrf_token(session.csrf_token, token_to_verify)

    if outcome not in {"success", "fail"}:
        raise DomainError(
            "VALIDATION", 422, "Invalid outcome parameter: must be success or fail"
        )

    outcome_literal: Literal["success", "fail"] = (
        "success" if outcome == "success" else "fail"
    )
    sim_secret = get_sim_secret()

    with unit_of_work() as conn:
        row = conn.execute(
            "SELECT * FROM payments WHERE public_id = ? AND user_id = ?;",
            (public_id, session.user_id),
        ).fetchone()
        if not row:
            raise DomainError("NOT_FOUND", 404, "Payment not found")

        payment = Payment(
            id=row["id"],
            public_id=row["public_id"],
            user_id=row["user_id"],
            purpose=row["purpose"],
            ref_table=row["ref_table"],
            ref_id=row["ref_id"],
            amount_paise=row["amount_paise"],
            status=row["status"],
            fulfillment=row["fulfillment"],
            term_id=row["term_id"],
        )

        event_outcome = dispatch_simulated_outcome(
            conn=conn,
            handlers=handlers,
            payment=payment,
            outcome=outcome_literal,
            secret=sim_secret,
        )

    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse(
            {
                "status": "ok",
                "outcome": event_outcome.outcome,
                "reason": event_outcome.reason,
            }
        )

    # Render the stored, ownership-checked payment state, not the requested outcome.
    return RedirectResponse(url=f"/pay/{public_id}?result=1", status_code=303)


# --- 2. Webhook (CSRF-Exempt, Signature-Only) ---


@router.post("/webhooks/payments")
async def post_payment_webhook(
    request: Request,
    handlers: Handlers = Depends(get_handlers),
) -> JSONResponse:
    """External-shaped payment webhook per CONTRACT §5."""
    raw_body = await request.body()
    sig_header = request.headers.get("X-Signature")
    client_ip = _get_client_ip(request)
    sim_secret = get_sim_secret()

    # 1. Untrusted phase: rate limit, signature, timestamp, body size, schema (zero DB writes)
    verify_webhook_request(
        raw_body=raw_body,
        signature_header=sig_header,
        client_ip=client_ip,
        secret=sim_secret,
    )

    # 2. Trusted phase inside atomic unit_of_work
    with unit_of_work() as conn:
        now_ts = clock.now()
        event_outcome = handle_event(
            conn=conn,
            handlers=handlers,
            raw_body=raw_body,
            signature_header=sig_header or "",
            now=now_ts,
        )

    return JSONResponse(
        {
            "status": "ok",
            "outcome": event_outcome.outcome,
            "reason": event_outcome.reason,
        },
        status_code=event_outcome.http_status,
    )


# --- 3. Payments Admin Routes ---


@router.get("/admin/payments")
def get_admin_payments(
    request: Request,
    refunded: int | None = None,
    problem: bool = False,
    unfulfilled: bool = False,
    unapplied: bool = False,
    session: Session = Depends(require_perm("payments.admin")),
) -> Response:
    """List payments with optional problem queue filtering per CONTRACT §3.1, §12."""
    conn = connect(get_db_path())
    try:
        query = "SELECT * FROM payments WHERE 1=1"
        params: list[Any] = []

        if problem or unfulfilled:
            query += (
                " AND (fulfillment = 'UNFULFILLED' OR status IN ('FAILED', 'EXPIRED'))"
            )

        query += " ORDER BY id DESC LIMIT 100;"
        rows = conn.execute(query, params).fetchall()
        payments = [dict(r) for r in rows]

        unapplied_events = []
        if problem or unapplied:
            ue_rows = conn.execute(
                "SELECT * FROM payment_events WHERE outcome = 'UNAPPLIED_RECEIPT' AND resolution IS NULL ORDER BY id DESC;"
            ).fetchall()
            unapplied_events = [dict(r) for r in ue_rows]

        data = {
            "payments": payments,
            "unapplied_receipts": unapplied_events,
            "csrf_token": session.csrf_token,
            "problem": problem,
            "unfulfilled": unfulfilled,
            "unapplied": unapplied,
            "refunded_payment_id": next(
                (
                    p["id"]
                    for p in payments
                    if p["id"] == refunded and p["status"] == "REFUNDED"
                ),
                None,
            ),
        }

        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse(
                {"payments": payments, "unapplied_receipts": unapplied_events}
            )

        return templates.TemplateResponse(
            request=request,
            name="payments/admin_payments.html",
            context=data,
        )
    finally:
        conn.close()


@router.post("/admin/payments/{payment_id}/refund")
def post_admin_refund(
    request: Request,
    payment_id: int,
    csrf_token: Annotated[str | None, Form()] = None,
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    session: Session = Depends(require_perm("payments.admin")),
    handlers: Handlers = Depends(get_handlers),
) -> Response:
    """Issue a full refund for a payment per CONTRACT §8."""
    token_to_verify = csrf_token or x_csrf_token
    verify_csrf_token(session.csrf_token, token_to_verify)

    with unit_of_work() as conn:
        refund_payment(
            conn, handlers=handlers, payment_id=payment_id, actor_id=session.user_id
        )

    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"status": "ok", "refunded": payment_id})
    return RedirectResponse(
        url=f"/admin/payments?refunded={payment_id}", status_code=303
    )


@router.post("/admin/payments/{payment_id}/fulfill")
def post_admin_fulfill(
    request: Request,
    payment_id: int,
    csrf_token: Annotated[str | None, Form()] = None,
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    session: Session = Depends(require_perm("payments.admin")),
    handlers: Handlers = Depends(get_handlers),
) -> Response:
    """Manually fulfill an unfulfilled obligation per CONTRACT §3.1."""
    token_to_verify = csrf_token or x_csrf_token
    verify_csrf_token(session.csrf_token, token_to_verify)

    with unit_of_work() as conn:
        resolve_unfulfilled(
            conn,
            handlers=handlers,
            payment_id=payment_id,
            action="FULFILL",
            actor_id=session.user_id,
        )

    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"status": "ok", "fulfilled": payment_id})
    return RedirectResponse(url="/admin/payments?problem=1", status_code=303)


@router.post("/admin/payment-events/{event_id}/resolve")
def post_admin_resolve_receipt(
    request: Request,
    event_id: int,
    action: Annotated[str, Form()],
    note: Annotated[str, Form()] = "",
    csrf_token: Annotated[str | None, Form()] = None,
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    session: Session = Depends(require_perm("payments.admin")),
) -> Response:
    """Resolve an unapplied receipt event per CONTRACT §3.1."""
    token_to_verify = csrf_token or x_csrf_token
    verify_csrf_token(session.csrf_token, token_to_verify)

    if action not in {"REFUND", "DISMISS"}:
        raise DomainError("VALIDATION", 422, "Action must be REFUND or DISMISS")

    action_literal: Literal["REFUND", "DISMISS"] = (
        "REFUND" if action == "REFUND" else "DISMISS"
    )

    with unit_of_work() as conn:
        resolve_receipt(
            conn,
            event_row_id=event_id,
            action=action_literal,
            actor_id=session.user_id,
            note=note,
        )

    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse(
            {"status": "ok", "resolved_event": event_id, "action": action}
        )
    return RedirectResponse(url="/admin/payments?problem=1", status_code=303)
