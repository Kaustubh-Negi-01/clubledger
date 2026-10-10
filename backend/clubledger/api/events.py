# In plain English: Serves event discovery, ticket booking, admission and event reports.
"""Events routes per CONTRACT.md §12."""

import base64
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from clubledger.config import get_db_path
from clubledger.core import clock, idgen
from clubledger.core.auth import (
    COOKIE_SESSION,
    get_current_session,
    get_user_permissions,
    load_session,
    require_perm,
    verify_csrf,
)
from clubledger.core.db import connect, unit_of_work
from clubledger.core.errors import DomainError
from clubledger.core.types import Session
from clubledger.events.service import (
    _compute_ticket_price_fallback,
    _genuine_ticket_price,
    check_in,
    create_hold,
    event_report,
    get_available_seats,
)

router = APIRouter(tags=["events"])

from clubledger.paths import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Formatting only: keep stored UTC times and all booking rules unchanged.
from clubledger.presentation.event_display import event_date, event_time

templates.env.filters["event_date"] = event_date
templates.env.filters["event_time"] = event_time


def get_optional_session(request: Request) -> Session | None:
    """Resolve session if present, otherwise return None for public routes."""
    raw_token = request.cookies.get(COOKIE_SESSION)
    if not raw_token:
        return None
    try:
        conn = connect(get_db_path())
        try:
            return load_session(conn, raw_token)
        finally:
            conn.close()
    except Exception:
        return None


def require_events_manage_or_finance_view(
    session: Session = Depends(get_current_session),
) -> Session:
    """Dependency: verify caller has events.manage or finance.view permission."""
    conn = connect(get_db_path())
    try:
        perms = get_user_permissions(conn, session.user_id)
        if "events.manage" not in perms and "finance.view" not in perms:
            raise DomainError(
                "FORBIDDEN", 403, "Missing events.manage or finance.view permission"
            )
        return session
    finally:
        conn.close()


@router.get("/events", response_class=HTMLResponse)
def get_events_list(request: Request) -> Response:
    """Public listing of events on sale with available seats and prices."""
    session = get_optional_session(request)
    conn = connect(get_db_path())
    try:
        now_str = clock.now()
        rows = conn.execute(
            "SELECT id, term_id, title, venue, starts_at, ends_at, capacity, "
            "       member_price_paise, public_price_paise, max_per_order, status "
            "FROM events WHERE status = 'ON_SALE' ORDER BY starts_at ASC;"
        ).fetchall()

        events_data = []
        for r in rows:
            avail = get_available_seats(conn, r["id"], r["capacity"], now_str)
            events_data.append(
                {
                    "id": r["id"],
                    "title": r["title"],
                    "venue": r["venue"],
                    "starts_at": r["starts_at"],
                    "ends_at": r["ends_at"],
                    "capacity": r["capacity"],
                    "member_price_paise": r["member_price_paise"],
                    "public_price_paise": r["public_price_paise"],
                    "member_price_inr": f"{r['member_price_paise'] / 100:.2f}",
                    "public_price_inr": f"{r['public_price_paise'] / 100:.2f}",
                    "available_seats": avail,
                }
            )

        return templates.TemplateResponse(
            request=request,
            name="events/list.html",
            context={
                "session": session,
                "events": events_data,
            },
        )
    finally:
        conn.close()


@router.get("/events/{event_id}", response_class=HTMLResponse)
def get_event_detail(request: Request, event_id: int) -> Response:
    """Public event detail and booking form (shows server-computed tier for logged-in user)."""
    session = get_optional_session(request)
    conn = connect(get_db_path())
    try:
        now_str = clock.now()
        event_row = conn.execute(
            "SELECT * FROM events WHERE id = ?;", (event_id,)
        ).fetchone()

        if not event_row:
            raise DomainError("NOT_FOUND", 404, "Event not found")

        # Hide draft events from public per EVT-01
        if event_row["status"] != "ON_SALE":
            raise DomainError("NOT_FOUND", 404, "Event is not currently on sale")

        avail = get_available_seats(conn, event_id, event_row["capacity"], now_str)

        user_price_paise = event_row["public_price_paise"]
        user_tier = "PUBLIC"
        idemp_key = None
        csrf_tok = None

        if session:
            csrf_tok = session.csrf_token
            idemp_key = idgen.generate_idempotency_key()
            if _genuine_ticket_price is not None:
                user_price_paise, user_tier = _genuine_ticket_price(
                    conn, event_id, session.user_id, now_str
                )
            else:
                user_price_paise, user_tier = _compute_ticket_price_fallback(
                    conn, event_row, session.user_id, now_str
                )

        return templates.TemplateResponse(
            request=request,
            name="events/detail.html",
            context={
                "session": session,
                "csrf_token": csrf_tok,
                "idempotency_key": idemp_key,
                "event": event_row,
                "available_seats": avail,
                "member_price_inr": f"{event_row['member_price_paise'] / 100:.2f}",
                "public_price_inr": f"{event_row['public_price_paise'] / 100:.2f}",
                "user_price_inr": f"{user_price_paise / 100:.2f}",
                "user_price_tier": user_tier,
            },
        )
    finally:
        conn.close()


@router.post("/events/{event_id}/hold")
def post_event_hold(
    request: Request,
    event_id: int,
    qty: Annotated[int, Form(...)],
    idempotency_key: Annotated[str, Form(...)],
    csrf_token: Annotated[str, Form(...)],
    session: Session = Depends(get_current_session),
) -> Response:
    """Reserve tickets under a capacity hold; redirect to payment or directly to tickets if free."""
    verify_csrf(session, csrf_token)
    with unit_of_work() as conn:
        hold, payment = create_hold(
            conn,
            user_id=session.user_id,
            event_id=event_id,
            qty=qty,
            idempotency_key=idempotency_key,
        )

        if payment is not None:
            return RedirectResponse(url=f"/pay/{payment.public_id}", status_code=303)

        # Free tickets: redirect to first ticket
        ticket_row = conn.execute(
            "SELECT id FROM tickets WHERE hold_id = ? ORDER BY seat_index ASC LIMIT 1;",
            (hold.id,),
        ).fetchone()
        ticket_id = ticket_row["id"] if ticket_row else 1
        return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)


@router.get("/tickets/{ticket_id}", response_class=HTMLResponse)
def get_ticket(
    request: Request,
    ticket_id: int,
    session: Session = Depends(get_current_session),
) -> Response:
    """Render owned ticket with seat code and optional QR."""
    conn = connect(get_db_path())
    try:
        ticket = conn.execute(
            "SELECT t.id, t.event_id, t.seat_index, t.user_id, t.code, t.price_paise, "
            "       t.price_tier, t.status, t.used_at, t.created_at, "
            "       e.title AS event_title, e.venue AS event_venue, "
            "       e.starts_at AS event_starts_at, e.ends_at AS event_ends_at, "
            "       u.name AS user_name "
            "FROM tickets t "
            "JOIN events e ON t.event_id = e.id "
            "JOIN users u ON t.user_id = u.id "
            "WHERE t.id = ?;",
            (ticket_id,),
        ).fetchone()

        if not ticket:
            raise DomainError("NOT_FOUND", 404, "Ticket not found")

        if ticket["user_id"] != session.user_id:
            raise DomainError("NOT_FOUND", 404, "Ticket not found")

        qr_data = None
        try:
            import qrcode  # type: ignore[import-untyped]
            import io

            qr = qrcode.QRCode(box_size=4, border=4)
            qr.add_data(ticket["code"])
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            qr_data = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"
        except Exception:
            qr_data = None

        return templates.TemplateResponse(
            request=request,
            name="events/ticket.html",
            context={
                "session": session,
                "ticket": ticket,
                "price_inr": f"{ticket['price_paise'] / 100:.2f}",
                "qr_data": qr_data,
            },
        )
    finally:
        conn.close()


@router.get("/checkin/{event_id}", response_class=HTMLResponse)
def get_checkin(
    request: Request,
    event_id: int,
    session: Session = Depends(require_perm("events.checkin")),
) -> Response:
    """Staff check-in form for scanning QR or entering manual ticket code."""
    conn = connect(get_db_path())
    try:
        event = conn.execute(
            "SELECT * FROM events WHERE id = ?;", (event_id,)
        ).fetchone()
        if not event:
            raise DomainError("NOT_FOUND", 404, "Event not found")
        return templates.TemplateResponse(
            request=request,
            name="events/checkin.html",
            context={
                "session": session,
                "csrf_token": session.csrf_token,
                "event": event,
                "result": None,
                "scanned_code": None,
            },
        )
    finally:
        conn.close()


@router.post("/checkin/{event_id}/scan", response_class=HTMLResponse)
def post_checkin_scan(
    request: Request,
    event_id: int,
    code: Annotated[str, Form(...)],
    csrf_token: Annotated[str, Form(...)],
    session: Session = Depends(require_perm("events.checkin")),
) -> Response:
    """Staff check-in verification."""
    verify_csrf(session, csrf_token)
    with unit_of_work() as conn:
        event = conn.execute(
            "SELECT * FROM events WHERE id = ?;", (event_id,)
        ).fetchone()
        if not event:
            raise DomainError("NOT_FOUND", 404, "Event not found")
        from clubledger.core.ratelimit import enforce_rate_limit

        enforce_rate_limit(f"checkin:{session.user_id}", limit=120, window_seconds=60)
        result = check_in(conn, event_id=event_id, code=code, staff_id=session.user_id)
        status_code = 200
        if result.status == "ALREADY_USED":
            status_code = 409
        elif result.status == "REJECTED":
            status_code = 422

        return templates.TemplateResponse(
            request=request,
            name="events/checkin.html",
            context={
                "session": session,
                "csrf_token": session.csrf_token,
                "event": event,
                "result": result,
                "scanned_code": code,
            },
            status_code=status_code,
        )


@router.get("/admin/events/{event_id}/report", response_class=HTMLResponse)
def get_admin_event_report(
    request: Request,
    event_id: int,
    session: Session = Depends(require_events_manage_or_finance_view),
) -> Response:
    """Admin event financial and attendance report per CONTRACT §11, §12."""
    conn = connect(get_db_path())
    try:
        event = conn.execute(
            "SELECT * FROM events WHERE id = ?;", (event_id,)
        ).fetchone()
        if not event:
            raise DomainError("NOT_FOUND", 404, "Event not found")
        report = event_report(conn, event_id)
        return templates.TemplateResponse(
            request=request,
            name="events/report.html",
            context={
                "session": session,
                "event": event,
                "report": report,
                "gross_inr": f"{report.gross / 100:.2f}",
                "refunded_inr": f"{report.refunded / 100:.2f}",
                "net_proceeds_inr": f"{report.net_proceeds / 100:.2f}",
            },
        )
    finally:
        conn.close()
