# In plain English: Serves joining, membership cards and officer membership verification.
"""Membership routes per CONTRACT.md §12."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from clubledger.config import get_db_path
from clubledger.core import clock, idgen
from clubledger.core.auth import get_current_session, require_perm, verify_csrf
from clubledger.core.db import connect, unit_of_work
from clubledger.core.errors import DomainError
from clubledger.core.types import Session
from clubledger.membership.service import lookup_member, start_join

router = APIRouter(tags=["membership"])

from clubledger.paths import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/join", response_class=HTMLResponse)
def get_join(
    request: Request, session: Session = Depends(get_current_session)
) -> Response:
    """Render plan list and join form with server-issued idempotency key."""
    conn = connect(get_db_path())
    try:
        plans = conn.execute(
            "SELECT id, code, name, dues_paise, ticket_discount_bps, merch_discount_bps "
            "FROM membership_plans WHERE is_active = 1 ORDER BY dues_paise ASC;"
        ).fetchall()
        memberships = conn.execute(
            "SELECT m.*,p.name AS plan_name,pay.status AS payment_status FROM memberships m JOIN membership_plans p ON p.id=m.plan_id LEFT JOIN payments pay ON pay.id=m.payment_id WHERE m.user_id=? ORDER BY m.starts_at DESC",
            (session.user_id,),
        ).fetchall()
        idemp_key = idgen.generate_idempotency_key()
        return templates.TemplateResponse(
            request=request,
            name="membership/join.html",
            context={
                "session": session,
                "csrf_token": session.csrf_token,
                "plans": plans,
                "memberships": memberships,
                "has_active_membership": any(
                    m["status"] == "ACTIVE"
                    and m["starts_at"] <= clock.now() < m["expires_at"]
                    for m in memberships
                ),
                "now": clock.now(),
                "idempotency_key": idemp_key,
                "error": None,
            },
        )
    finally:
        conn.close()


@router.post("/join")
def post_join(
    request: Request,
    plan_id: Annotated[int, Form(...)],
    idempotency_key: Annotated[str, Form(...)],
    csrf_token: Annotated[str, Form(...)],
    session: Session = Depends(get_current_session),
) -> Response:
    """Start join workflow and redirect to payment simulator."""
    verify_csrf(session, csrf_token)
    with unit_of_work() as conn:
        payment = start_join(conn, session.user_id, plan_id, idempotency_key)
        return RedirectResponse(url=f"/pay/{payment.public_id}", status_code=303)


@router.get("/members/card", response_class=HTMLResponse)
def get_member_card(
    request: Request, session: Session = Depends(get_current_session)
) -> Response:
    """Display user's active membership card with member code and validity."""
    conn = connect(get_db_path())
    try:
        now_str = clock.now()
        row = conn.execute(
            "SELECT m.id, m.membership_year, m.status, m.starts_at, m.expires_at, "
            "       m.member_code, m.qr_token, p.name AS plan_name, u.name AS user_name "
            "FROM memberships m "
            "JOIN membership_plans p ON m.plan_id = p.id "
            "JOIN users u ON m.user_id = u.id "
            "WHERE m.user_id = ? AND m.status = 'ACTIVE' "
            "  AND m.starts_at <= ? AND m.expires_at > ? "
            "ORDER BY m.id DESC LIMIT 1;",
            (session.user_id, now_str, now_str),
        ).fetchone()
        return templates.TemplateResponse(
            request=request,
            name="membership/card.html",
            context={
                "session": session,
                "membership": row,
                "now": now_str,
                "qr_data": __import__(
                    "clubledger.presentation.qr", fromlist=["image_data"]
                ).image_data(row["qr_token"])
                if row
                else None,
            },
        )
    finally:
        conn.close()


@router.get("/verify", response_class=HTMLResponse)
def get_verify(
    request: Request,
    session: Session = Depends(require_perm("members.verify")),
) -> Response:
    """Render staff membership verification lookup form."""
    return templates.TemplateResponse(
        request=request,
        name="membership/verify.html",
        context={
            "session": session,
            "csrf_token": session.csrf_token,
            "result": None,
            "error": None,
        },
    )


@router.post("/verify/lookup", response_class=HTMLResponse)
def post_verify_lookup(
    request: Request,
    csrf_token: Annotated[str, Form(...)],
    code: Annotated[str | None, Form()] = None,
    qr_token: Annotated[str | None, Form()] = None,
    session: Session = Depends(require_perm("members.verify")),
) -> Response:
    """Lookup member by code or QR token (staff verification)."""
    verify_csrf(session, csrf_token)
    from clubledger.core.ratelimit import enforce_rate_limit

    enforce_rate_limit(f"verify:{session.user_id}", limit=60, window_seconds=60)
    conn = connect(get_db_path())
    try:
        result = lookup_member(
            conn,
            code=code.strip() if code else None,
            qr_token=qr_token.strip() if qr_token else None,
            at=clock.now(),
        )
        return templates.TemplateResponse(
            request=request,
            name="membership/verify.html",
            context={
                "session": session,
                "csrf_token": session.csrf_token,
                "result": result,
                "searched_code": code or qr_token,
                "error": None,
            },
        )
    finally:
        conn.close()
