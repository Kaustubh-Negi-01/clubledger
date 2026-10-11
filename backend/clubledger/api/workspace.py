# In plain English: Serves dashboard and club operations including announcements, tasks, inventory, close and handover.
"""Browser workflows connecting the club's operational and financial domains."""

import json
from decimal import Decimal, InvalidOperation
from typing import Annotated
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse, JSONResponse
from clubledger.security.auth import (
    get_current_session,
    require_perm,
    verify_csrf,
    get_user_permissions,
    deactivate_user,
)
from clubledger.core.types import Session, Line
from clubledger.core import clock
from clubledger.core.db import connect, unit_of_work
from clubledger.config import get_db_path, get_env
from clubledger.core.errors import DomainError
from clubledger.core.pricing import active_membership
from clubledger.presentation.ui import render
from clubledger.tasks import service as tasks
from clubledger.comms import service as comms
from clubledger.close import service as close
from clubledger.reports import service as reports
from clubledger.payments.service import settle_payments

router = APIRouter()
Auth = Annotated[Session, Depends(get_current_session)]
Token = Annotated[str, Form()]


def money(value):
    """Convert a positive rupee amount to exact integer paise; reject excess decimal places."""
    try:
        amount = Decimal(value)
        if (
            not amount.is_finite()
            or amount <= 0
            or amount * 100 != (amount * 100).to_integral_value()
            or amount > 10000000
        ):
            raise InvalidOperation
        return int(amount * 100)
    except (InvalidOperation, ValueError):
        raise DomainError(
            "VALIDATION",
            422,
            "Enter a positive rupee amount with at most two decimal places.",
        )


def open_term(conn):
    """Find the open financial period or report that the term is closed."""
    row = conn.execute("SELECT * FROM terms WHERE status='OPEN'").fetchone()
    if not row:
        raise DomainError("TERM_CLOSED", 409)
    return row


def redirect(path):
    """Return a 303 redirect so the browser follows a form submission with a GET."""
    return RedirectResponse(path, status_code=303)


@router.get("/dashboard")
def dashboard(request: Request, session: Auth):
    """Handle GET /dashboard. Dashboard."""
    conn = connect(get_db_path())
    try:
        term = open_term(conn)
        membership = active_membership(conn, session.user_id, clock.now())
        tickets = conn.execute(
            "SELECT t.*,e.title,e.starts_at FROM tickets t JOIN events e ON e.id=t.event_id WHERE t.user_id=? ORDER BY t.id DESC LIMIT 8",
            (session.user_id,),
        ).fetchall()
        events = conn.execute(
            "SELECT e.*,e.capacity-(SELECT COUNT(*) FROM tickets t WHERE t.event_id=e.id AND t.status IN ('ISSUED','USED')) AS remaining FROM events e WHERE status='ON_SALE' ORDER BY starts_at LIMIT 4"
        ).fetchall()
        announcements = conn.execute(
            "SELECT * FROM announcements WHERE status='PUBLISHED' ORDER BY published_at DESC,id DESC LIMIT 3"
        ).fetchall()
        own_tasks = conn.execute(
            "SELECT t.*,f.title AS fundraiser_title FROM tasks t JOIN fundraisers f ON f.id=t.fundraiser_id WHERE t.owner_user_id=? AND t.status<>'DONE' ORDER BY t.due_at LIMIT 4",
            (session.user_id,),
        ).fetchall()
        cash = (
            reports.cash_summary(conn, term["id"])
            if "finance.view" in get_user_permissions(conn, session.user_id)
            else None
        )
        return render(
            request,
            "dashboard.html",
            membership=membership,
            tickets=tickets,
            events=events,
            announcements=announcements,
            tasks=own_tasks,
            cash=cash,
            term=term,
        )
    finally:
        conn.close()


@router.get("/announcements")
def announcements(request: Request):
    """Handle GET /announcements. Announcements."""
    conn = connect(get_db_path())
    try:
        rows = conn.execute(
            "SELECT a.*,u.name AS author FROM announcements a JOIN users u ON u.id=a.author_id WHERE a.status='PUBLISHED' ORDER BY a.published_at DESC,a.id DESC"
        ).fetchall()
        return render(request, "announcements.html", announcements=rows)
    finally:
        conn.close()


@router.get("/announcements/{announcement_id}")
def announcement(request: Request, announcement_id: int):
    """Handle GET /announcements/{announcement_id}. Announcement."""
    conn = connect(get_db_path())
    try:
        row = conn.execute(
            "SELECT a.*,u.name AS author FROM announcements a JOIN users u ON u.id=a.author_id WHERE a.id=? AND a.status='PUBLISHED'",
            (announcement_id,),
        ).fetchone()
        if not row:
            raise DomainError("NOT_FOUND", 404)
        return render(request, "announcements.html", announcements=[row])
    finally:
        conn.close()


@router.post("/subscribe")
async def subscribe(request: Request, email: Annotated[str, Form()], csrf_token: Token):
    """Handle POST /subscribe. Subscribe."""
    from clubledger.security.csrf import verify_pre_session_csrf
    from clubledger.security.ratelimit import enforce_rate_limit

    # A subscriber need not be a club member; pre-session CSRF is still required.
    verify_pre_session_csrf(request, csrf_token)
    enforce_rate_limit(
        "subscribe:" + (request.client.host if request.client else "local"),
        limit=10,
        window_seconds=3600,
    )
    with unit_of_work() as conn:
        comms.subscribe(conn, email)
    return redirect("/announcements?notice=Subscribed")


@router.get("/unsubscribe/{token}")
def unsubscribe_page(request: Request, token: str):
    """Handle GET /unsubscribe/{token}. Unsubscribe page."""
    conn = connect(get_db_path())
    try:
        row = conn.execute(
            "SELECT email FROM subscribers WHERE unsub_token=?", (token,)
        ).fetchone()
        if not row:
            raise DomainError("NOT_FOUND", 404)
        return render(request, "unsubscribe.html", email=row["email"], token=token)
    finally:
        conn.close()


@router.post("/unsubscribe/{token}")
def unsubscribe(request: Request, token: str, csrf_token: Token):
    """Handle POST /unsubscribe/{token}. Unsubscribe."""
    from clubledger.security.csrf import verify_pre_session_csrf

    verify_pre_session_csrf(request, csrf_token)
    with unit_of_work() as conn:
        comms.unsubscribe(conn, token)
    return redirect("/announcements?notice=Unsubscribed")


@router.get("/admin/announcements")
def manage_announcements(
    request: Request,
    session: Annotated[Session, Depends(require_perm("comms.publish"))],
):
    """Handle GET /admin/announcements. Manage announcements."""
    conn = connect(get_db_path())
    try:
        return render(
            request,
            "manage_announcements.html",
            announcements=conn.execute(
                "SELECT * FROM announcements ORDER BY id DESC"
            ).fetchall(),
            subscribers=conn.execute(
                "SELECT COUNT(*) FROM subscribers WHERE status='SUBSCRIBED'"
            ).fetchone()[0],
        )
    finally:
        conn.close()


@router.post("/admin/announcements")
def draft_announcement(
    request: Request,
    session: Annotated[Session, Depends(require_perm("comms.publish"))],
    csrf_token: Token,
    title: Annotated[str, Form()],
    body: Annotated[str, Form()],
):
    """Handle POST /admin/announcements. Draft announcement."""
    verify_csrf(session, csrf_token)
    with unit_of_work() as conn:
        comms.create_announcement(conn, session.user_id, title, body)
    return redirect("/admin/announcements?notice=Draft+saved")


@router.post("/admin/announcements/{announcement_id}/publish")
def publish(
    request: Request,
    background_tasks: BackgroundTasks,
    announcement_id: int,
    session: Annotated[Session, Depends(require_perm("comms.publish"))],
    csrf_token: Token,
):
    """Handle POST /admin/announcements/{announcement_id}/publish. Publish."""
    verify_csrf(session, csrf_token)
    with unit_of_work() as conn:
        comms.publish(conn, announcement_id)
    if get_env() == "prod":
        from clubledger.comms.delivery import deliver_announcement

        background_tasks.add_task(deliver_announcement, announcement_id)
    return redirect("/admin/announcements?notice=Published")


@router.get("/dev/mail")
def mail(request: Request, session: Auth):
    """Handle GET /dev/mail. Mail."""
    if get_env() not in ("dev", "test"):
        raise DomainError("NOT_FOUND", 404)
    conn = connect(get_db_path())
    try:
        if "comms.mail_viewer" not in get_user_permissions(conn, session.user_id):
            raise DomainError("FORBIDDEN", 403)
        rows = conn.execute(
            "SELECT * FROM mail_outbox ORDER BY id DESC"
        ).fetchall()
        return render(request, "mail.html", messages=rows)
    finally:
        conn.close()


@router.post("/dev/mail/process")
def process_mail(request: Request, session: Auth, csrf_token: Token):
    """Handle POST /dev/mail/process. Process mail."""
    verify_csrf(session, csrf_token)
    if get_env() not in ("dev", "test"):
        raise DomainError("NOT_FOUND", 404)
    with unit_of_work() as conn:
        if "comms.mail_viewer" not in get_user_permissions(conn, session.user_id):
            raise DomainError("FORBIDDEN", 403)
        comms.process_mail_outbox(conn)
    return redirect("/dev/mail?notice=Mail+processed+locally")


@router.post("/dev/mail/reminders")
def renewal_reminders(request: Request, session: Auth, csrf_token: Token):
    """Handle POST /dev/mail/reminders. Renewal reminders."""
    verify_csrf(session, csrf_token)
    if get_env() not in ("dev", "test"):
        raise DomainError("NOT_FOUND", 404)
    with unit_of_work() as conn:
        if "comms.mail_viewer" not in get_user_permissions(conn, session.user_id):
            raise DomainError("FORBIDDEN", 403)
        count = comms.send_reminders(conn)
    return redirect(f"/dev/mail?notice=Queued+{count}+renewal+reminders")


@router.get("/fundraisers")
def fundraisers(request: Request, session: Auth):
    """Handle GET /fundraisers. Fundraisers."""
    conn = connect(get_db_path())
    try:
        rows = [
            tasks.get_fundraiser(conn, row["id"])
            for row in conn.execute("SELECT id FROM fundraisers ORDER BY id DESC")
        ]
        return render(request, "fundraisers.html", fundraisers=rows)
    finally:
        conn.close()


@router.post("/fundraisers")
def fundraiser_create(
    request: Request,
    session: Annotated[Session, Depends(require_perm("tasks.manage"))],
    csrf_token: Token,
    title: Annotated[str, Form()],
    goal: Annotated[str, Form()],
):
    """Handle POST /fundraisers. Fundraiser create."""
    verify_csrf(session, csrf_token)
    with unit_of_work() as conn:
        tasks.create_fundraiser(
            conn,
            term_id=open_term(conn)["id"],
            title=title,
            goal_paise=money(goal),
            status="ACTIVE",
        )
    return redirect("/fundraisers?notice=Fundraiser+created")


@router.get("/fundraisers/{fundraiser_id}/board")
def board(request: Request, fundraiser_id: int, session: Auth):
    """Handle GET /fundraisers/{fundraiser_id}/board. Board."""
    conn = connect(get_db_path())
    try:
        data = tasks.get_fundraiser_board(conn, fundraiser_id)
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse(data)
        return render(
            request,
            "board.html",
            board=data,
            fundraiser=tasks.get_fundraiser(conn, fundraiser_id),
            users=conn.execute(
                "SELECT id,name FROM users WHERE is_active=1 ORDER BY name"
            ).fetchall(),
        )
    finally:
        conn.close()


@router.post("/fundraisers/{fundraiser_id}/tasks")
def task_create(
    request: Request,
    fundraiser_id: int,
    session: Annotated[Session, Depends(require_perm("tasks.manage"))],
    csrf_token: Token,
    title: Annotated[str, Form()],
    owner_user_id: Annotated[int, Form()],
    due_at: Annotated[str, Form()],
):
    """Handle POST /fundraisers/{fundraiser_id}/tasks. Task create."""
    verify_csrf(session, csrf_token)
    from datetime import datetime, timezone

    try:
        deadline = (
            datetime.fromisoformat(due_at)
            .replace(tzinfo=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except ValueError:
        raise DomainError("VALIDATION", 422, "Enter a valid deadline in UTC.")
    with unit_of_work() as conn:
        tasks.create_task(
            conn,
            fundraiser_id=fundraiser_id,
            title=title,
            owner_user_id=owner_user_id,
            due_at=deadline,
        )
    return redirect(f"/fundraisers/{fundraiser_id}/board?notice=Task+created")


@router.post("/tasks/{task_id}/status")
def task_status(
    request: Request,
    task_id: int,
    session: Auth,
    csrf_token: Token,
    status: Annotated[str, Form()],
):
    """Handle POST /tasks/{task_id}/status. Task status."""
    verify_csrf(session, csrf_token)
    with unit_of_work() as conn:
        tasks.update_task_status(
            conn,
            task_id=task_id,
            status=status,
            actor_user_id=session.user_id,
            is_staff="tasks.manage" in get_user_permissions(conn, session.user_id),
        )
        row = conn.execute(
            "SELECT fundraiser_id FROM tasks WHERE id=?", (task_id,)
        ).fetchone()
    return redirect(f"/fundraisers/{row['fundraiser_id']}/board?notice=Task+updated")


@router.get("/expenses")
def expenses(request: Request, session: Auth):
    """Handle GET /expenses. Expenses."""
    conn = connect(get_db_path())
    try:
        perms = get_user_permissions(conn, session.user_id)
        staff = bool(perms.intersection({"expenses.approve", "expenses.pay"}))
        rows = conn.execute(
            "SELECT e.*,u.name AS submitter,a.name AS category FROM expenses e JOIN users u ON u.id=e.submitter_id JOIN accounts a ON a.id=e.category_account_id WHERE (?=1 OR e.submitter_id=?) ORDER BY e.id DESC",
            (int(staff), session.user_id),
        ).fetchall()
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"expenses": [dict(row) for row in rows]})
        receipts = conn.execute(
            "SELECT r.* FROM receipts r JOIN expenses e ON e.id=r.expense_id WHERE (?=1 OR e.submitter_id=?)",
            (int("receipts.view_all" in perms), session.user_id),
        ).fetchall()
        return render(
            request,
            "expenses.html",
            expenses=rows,
            receipts=receipts,
            categories=conn.execute(
                "SELECT id,code,name FROM accounts WHERE type='EXPENSE' ORDER BY code"
            ).fetchall(),
            fundraisers=conn.execute("SELECT id,title FROM fundraisers").fetchall(),
            tasks=conn.execute("SELECT id,title,fundraiser_id FROM tasks").fetchall(),
            events=conn.execute("SELECT id,title FROM events").fetchall(),
        )
    finally:
        conn.close()


@router.get("/expenses/new")
def expense_new(request: Request, session: Auth):
    """Handle GET /expenses/new. Expense new."""
    return redirect("/expenses")


@router.post("/expenses/submit")
def expense_submit(
    request: Request,
    session: Auth,
    csrf_token: Token,
    category_account_id: Annotated[int, Form()],
    amount: Annotated[str, Form()],
    description: Annotated[str, Form()],
    event_id: Annotated[str, Form()] = "",
    fundraiser_id: Annotated[str, Form()] = "",
    task_id: Annotated[str, Form()] = "",
):
    """Handle POST /expenses/submit. Expense submit."""
    from clubledger.expenses.service import submit_expense

    verify_csrf(session, csrf_token)
    try:
        event = int(event_id) if event_id else None
        fundraiser = int(fundraiser_id) if fundraiser_id else None
        task = int(task_id) if task_id else None
    except ValueError:
        raise DomainError(
            "VALIDATION", 422, "Choose a valid event, fundraiser and task."
        )
    with unit_of_work() as conn:
        submit_expense(
            conn,
            submitter_id=session.user_id,
            category_account_id=category_account_id,
            amount_paise=money(amount),
            description=description,
            event_id=event,
            fundraiser_id=fundraiser,
            task_id=task,
        )
    return redirect("/expenses?notice=Expense+submitted")


@router.get("/admin/checkin")
def checkin_events(
    request: Request,
    session: Annotated[Session, Depends(require_perm("events.checkin"))],
):
    """Handle GET /admin/checkin. Checkin events."""
    conn = connect(get_db_path())
    try:
        return render(
            request,
            "checkin_select.html",
            events=conn.execute(
                "SELECT * FROM events WHERE status<>'CANCELLED' ORDER BY starts_at"
            ).fetchall(),
        )
    finally:
        conn.close()


@router.get("/admin/adjustments")
def adjustments(
    request: Request, session: Annotated[Session, Depends(require_perm("close.run"))]
):
    """Handle GET /admin/adjustments. Adjustments."""
    conn = connect(get_db_path())
    try:
        return render(
            request,
            "adjustments.html",
            terms=conn.execute("SELECT * FROM terms WHERE status='CLOSED'").fetchall(),
            accounts=conn.execute(
                "SELECT code,name FROM accounts ORDER BY code"
            ).fetchall(),
            entries=conn.execute(
                "SELECT * FROM journal_entries WHERE source_type='adjustment' ORDER BY id DESC"
            ).fetchall(),
        )
    finally:
        conn.close()


@router.post("/admin/adjustments")
def adjustment(
    request: Request,
    session: Annotated[Session, Depends(require_perm("close.run"))],
    csrf_token: Token,
    adjusts_term_id: Annotated[int, Form()],
    debit: Annotated[str, Form()],
    credit: Annotated[str, Form()],
    amount: Annotated[str, Form()],
    memo: Annotated[str, Form()],
    idempotency_key: Annotated[str, Form()],
):
    """Handle POST /admin/adjustments. Adjustment."""
    from clubledger.journal.service import post_entry
    import hashlib

    verify_csrf(session, csrf_token)
    if not memo.strip() or debit == credit:
        raise DomainError(
            "VALIDATION", 422, "Provide a correction memo and two different accounts."
        )
    value = money(amount)
    digest = hashlib.sha256(
        json.dumps(
            [adjusts_term_id, debit, credit, value, memo], separators=(",", ":")
        ).encode()
    ).hexdigest()
    with unit_of_work() as conn:
        old = conn.execute(
            "SELECT request_hash FROM idempotency_keys WHERE actor_user_id=? AND action='journal.adjust' AND key=?",
            (session.user_id, idempotency_key),
        ).fetchone()
        if old:
            if old["request_hash"] != digest:
                raise DomainError("IDEMPOTENCY_CONFLICT", 422)
            return redirect("/admin/adjustments?notice=Correction+already+recorded")
        source = conn.execute(
            "SELECT COALESCE(MAX(source_id),0)+1 FROM journal_entries WHERE source_type='adjustment'"
        ).fetchone()[0]
        result = post_entry(
            conn,
            term_id=open_term(conn)["id"],
            entry_date=clock.now(),
            source_type="adjustment",
            source_id=source,
            source_event="correction",
            memo=memo,
            lines=[Line(debit, value, 0), Line(credit, 0, value)],
            adjusts_term_id=adjusts_term_id,
        )
        conn.execute(
            "INSERT INTO idempotency_keys(actor_user_id,action,key,request_hash,result_ref,created_at) VALUES(?,'journal.adjust',?,?,?,?)",
            (session.user_id, idempotency_key, digest, str(result), clock.now()),
        )
    return redirect("/admin/adjustments?notice=Correction+posted+in+open+period")


@router.get("/admin/close")
def close_page(
    request: Request, session: Annotated[Session, Depends(require_perm("close.run"))]
):
    """Handle GET /admin/close. Close page."""
    conn = connect(get_db_path())
    try:
        term = open_term(conn)
        return render(
            request,
            "close.html",
            term=term,
            checks=close.checklist(conn, term["id"]),
            snapshots=conn.execute(
                "SELECT s.*,t.label FROM close_snapshots s JOIN terms t ON t.id=s.term_id ORDER BY s.id DESC"
            ).fetchall(),
        )
    finally:
        conn.close()


@router.post("/admin/close")
def close_period(
    request: Request,
    session: Annotated[Session, Depends(require_perm("close.run"))],
    csrf_token: Token,
    term_id: Annotated[int, Form()],
    confirmation: Annotated[str, Form()],
):
    """Handle POST /admin/close. Close period."""
    verify_csrf(session, csrf_token)
    if confirmation != "CLOSE":
        raise DomainError(
            "VALIDATION", 422, "Type CLOSE to confirm the irreversible snapshot."
        )
    with unit_of_work() as conn:
        close.run_close(conn, term_id, session.user_id)
    return redirect("/admin/close?notice=Period+closed+and+next+period+opened")


@router.get("/snapshots/{snapshot_id}")
def snapshot(
    request: Request,
    snapshot_id: int,
    session: Annotated[Session, Depends(require_perm("finance.view"))],
):
    """Handle GET /snapshots/{snapshot_id}. Snapshot."""
    conn = connect(get_db_path())
    try:
        row = conn.execute(
            "SELECT * FROM close_snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()
        if not row:
            raise DomainError("NOT_FOUND", 404)
        return render(
            request,
            "snapshot.html",
            snapshot=row,
            totals=json.loads(row["totals_json"]),
        )
    finally:
        conn.close()


@router.post("/admin/settle")
def settlement(
    request: Request,
    session: Annotated[Session, Depends(require_perm("payments.admin"))],
    csrf_token: Token,
):
    """Handle POST /admin/settle. Settlement."""
    verify_csrf(session, csrf_token)
    with unit_of_work() as conn:
        count = settle_payments(conn, as_of=clock.now())
    return redirect(f"/finance?notice=Settled+{count}+eligible+payments")


@router.post("/dev/advance-day")
def advance_demo(
    request: Request,
    session: Annotated[Session, Depends(require_perm("payments.admin"))],
    csrf_token: Token,
):
    """Handle POST /dev/advance-day. Advance demo."""
    verify_csrf(session, csrf_token)
    if get_env() not in ("dev", "test"):
        raise DomainError("NOT_FOUND", 404)
    clock.advance_demo_day()
    return redirect(
        "/auth/login?notice=Demo+clock+advanced+one+day.+Sign+in+again+then+settle+eligible+payments."
    )


@router.post("/admin/expire")
def expiration(
    request: Request,
    session: Annotated[Session, Depends(require_perm("payments.admin"))],
    csrf_token: Token,
):
    """Handle POST /admin/expire. Expiration."""
    verify_csrf(session, csrf_token)
    from clubledger.cli import handle_expire_holds

    handle_expire_holds()
    return redirect("/admin/close?notice=Expired+stale+reservations")


@router.get("/admin/handover")
def handover_page(
    request: Request, session: Annotated[Session, Depends(require_perm("handover.run"))]
):
    """Handle GET /admin/handover. Handover page."""
    conn = connect(get_db_path())
    try:
        return render(
            request,
            "handover.html",
            terms=conn.execute(
                "SELECT t.* FROM terms t JOIN close_snapshots s ON s.term_id=t.id WHERE t.status='CLOSED' AND NOT EXISTS(SELECT 1 FROM officer_handover h WHERE h.term_id=t.id)"
            ).fetchall(),
            users=conn.execute(
                "SELECT id,name,email FROM users WHERE is_active=1"
            ).fetchall(),
            roles=conn.execute("SELECT code FROM roles ORDER BY code").fetchall(),
            records=conn.execute(
                "SELECT h.*,f.name AS outgoing,t.name AS incoming FROM officer_handover h JOIN users f ON f.id=h.from_user_id JOIN users t ON t.id=h.to_user_id"
            ).fetchall(),
        )
    finally:
        conn.close()


@router.post("/admin/handover")
def handover(
    request: Request,
    session: Annotated[Session, Depends(require_perm("handover.run"))],
    csrf_token: Token,
    term_id: Annotated[int, Form()],
    from_user_id: Annotated[int, Form()],
    to_user_id: Annotated[int, Form()],
    role_codes: Annotated[list[str], Form()],
    notes: Annotated[str, Form()] = "",
):
    """Handle POST /admin/handover. Handover."""
    verify_csrf(session, csrf_token)
    with unit_of_work() as conn:
        close.run_handover(conn, term_id, from_user_id, to_user_id, role_codes, notes)
    return redirect("/admin/handover?notice=Handover+completed")


@router.get("/admin/members")
def members(
    request: Request,
    session: Annotated[Session, Depends(require_perm("members.manage"))],
):
    """Handle GET /admin/members. Members."""
    conn = connect(get_db_path())
    try:
        from clubledger.security.roles import require_administrator
        require_administrator(conn, session.user_id)
        return render(
            request,
            "members.html",
            users=conn.execute(
                "SELECT u.id,u.name,u.email,u.is_active,(SELECT m.status FROM memberships m WHERE m.user_id=u.id ORDER BY id DESC LIMIT 1) AS membership_status FROM users u ORDER BY u.id"
            ).fetchall(),
            roles=conn.execute("SELECT code FROM roles").fetchall(),
            grants=conn.execute(
                "SELECT ur.user_id,r.code FROM user_roles ur JOIN roles r ON r.id=ur.role_id WHERE ur.revoked_at IS NULL"
            ).fetchall(),
        )
    finally:
        conn.close()


@router.post("/admin/users/{user_id}/role")
def grant_role(
    request: Request,
    user_id: int,
    session: Annotated[Session, Depends(require_perm("users.manage"))],
    csrf_token: Token,
    role: Annotated[str, Form()],
    action: Annotated[str, Form()],
):
    """Handle POST /admin/users/{user_id}/role. Grant role."""
    verify_csrf(session, csrf_token)
    with unit_of_work() as conn:
        from clubledger.security.roles import require_administrator, protect_self
        require_administrator(conn, session.user_id)
        protect_self(session.user_id, user_id, action, role)
        row = conn.execute("SELECT id FROM roles WHERE code=?", (role,)).fetchone()
        if (
            not row
            or not conn.execute(
                "SELECT 1 FROM users WHERE id=? AND is_active=1", (user_id,)
            ).fetchone()
            or action not in ("grant", "revoke")
        ):
            raise DomainError("VALIDATION", 422)
        now = clock.now()
        if action == "grant":
            if not conn.execute(
                "SELECT 1 FROM user_roles WHERE user_id=? AND role_id=? AND revoked_at IS NULL",
                (user_id, row["id"]),
            ).fetchone():
                conn.execute(
                    "INSERT INTO user_roles(user_id,role_id,granted_at,created_at) VALUES(?,?,?,?)",
                    (user_id, row["id"], now, now),
                )
        else:
            if (
                role == "admin"
                and not conn.execute(
                    "SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id JOIN users u ON u.id=ur.user_id WHERE r.code='admin' AND ur.revoked_at IS NULL AND u.is_active=1 AND u.id<>?",
                    (user_id,),
                ).fetchone()
            ):
                raise DomainError(
                    "VALIDATION", 422, "Cannot remove the last active administrator."
                )
            conn.execute(
                "UPDATE user_roles SET revoked_at=? WHERE user_id=? AND role_id=? AND revoked_at IS NULL",
                (now, user_id, row["id"]),
            )
        conn.execute(
            "INSERT INTO audit_log(actor_user_id,action,entity,entity_id,detail,created_at) VALUES(?,'role_change','users',?,?,?)",
            (session.user_id, user_id, action + " " + role, now),
        )
    return redirect("/admin/members?notice=Role+updated")


@router.post("/admin/users/{user_id}/status")
def user_status(
    request: Request,
    user_id: int,
    session: Annotated[Session, Depends(require_perm("users.manage"))],
    csrf_token: Token,
    action: Annotated[str, Form()],
):
    """Handle POST /admin/users/{user_id}/status. User status."""
    verify_csrf(session, csrf_token)
    with unit_of_work() as conn:
        from clubledger.security.roles import require_administrator, protect_self
        require_administrator(conn, session.user_id)
        protect_self(session.user_id, user_id, action)
        if not conn.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
            raise DomainError("NOT_FOUND", 404)
        if action == "deactivate":
            if not conn.execute(
                "SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id JOIN users u ON u.id=ur.user_id WHERE r.code='admin' AND ur.revoked_at IS NULL AND u.is_active=1 AND u.id<>?",
                (user_id,),
            ).fetchone():
                raise DomainError(
                    "VALIDATION", 422, "At least one active administrator must remain."
                )
            deactivate_user(conn, user_id)
        elif action == "reactivate":
            conn.execute("UPDATE users SET is_active=1 WHERE id=?", (user_id,))
        else:
            raise DomainError("VALIDATION", 422)
        conn.execute(
            "INSERT INTO audit_log(actor_user_id,action,entity,entity_id,detail,created_at) VALUES(?,'user_status','users',?,?,?)",
            (session.user_id, user_id, action, clock.now()),
        )
    return redirect("/admin/members?notice=Account+status+updated")


@router.get("/admin/events")
def events_admin(
    request: Request,
    session: Annotated[Session, Depends(require_perm("events.manage"))],
    event_search: Annotated[str, Query(max_length=80)] = "",
    event_status: Annotated[str, Query()] = "ALL",
):
    """Handle GET /admin/events. Events admin."""
    conn = connect(get_db_path())
    try:
        normalized_search = event_search.strip().casefold()
        event_status = event_status.upper()
        allowed_statuses = {"ALL", "DRAFT", "ON_SALE", "CANCELLED", "COMPLETED"}
        if event_status not in allowed_statuses:
            event_status = "ALL"
        events = [
            event
            for event in conn.execute("SELECT * FROM events ORDER BY id DESC").fetchall()
            if (
                not normalized_search
                or normalized_search in event["title"].casefold()
                or normalized_search in event["venue"].casefold()
            )
            and (event_status == "ALL" or event["status"] == event_status)
        ]
        return render(
            request,
            "manage_events.html",
            events=events,
            event_search=event_search.strip(),
            event_status=event_status,
        )
    finally:
        conn.close()


@router.post("/admin/events")
def event_create(
    request: Request,
    session: Annotated[Session, Depends(require_perm("events.manage"))],
    csrf_token: Token,
    title: Annotated[str, Form()],
    venue: Annotated[str, Form()],
    starts_at: Annotated[str, Form()],
    ends_at: Annotated[str, Form()],
    capacity: Annotated[int, Form()],
    public_price: Annotated[str, Form()],
    member_price: Annotated[str, Form()],
):
    """Handle POST /admin/events. Event create."""
    verify_csrf(session, csrf_token)
    from datetime import datetime, timezone

    try:
        start = (
            datetime.fromisoformat(starts_at)
            .replace(tzinfo=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
        end = (
            datetime.fromisoformat(ends_at)
            .replace(tzinfo=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
        pub = 0 if Decimal(public_price) == 0 else money(public_price)
        mem = 0 if Decimal(member_price) == 0 else money(member_price)
    except (ValueError, InvalidOperation):
        raise DomainError("VALIDATION", 422, "Enter valid UTC event dates and prices.")
    if (
        not title.strip()
        or not venue.strip()
        or end <= start
        or capacity < 1
        or capacity > 100000
        or mem > pub
    ):
        raise DomainError(
            "VALIDATION", 422, "Check capacity, dates, title and member price."
        )
    with unit_of_work() as conn:
        conn.execute(
            "INSERT INTO events(term_id,title,venue,starts_at,ends_at,capacity,public_price_paise,member_price_paise,max_per_order,status,created_at) VALUES(?,?,?,?,?,?,?,?,4,'ON_SALE',?)",
            (
                open_term(conn)["id"],
                title,
                venue,
                start,
                end,
                capacity,
                pub,
                mem,
                clock.now(),
            ),
        )
    return redirect("/admin/events?notice=Event+created")


@router.post("/admin/events/{event_id}/cancel")
def event_cancel(
    request: Request,
    event_id: int,
    session: Annotated[Session, Depends(require_perm("events.manage"))],
    csrf_token: Token,
):
    """Handle POST /admin/events/{event_id}/cancel. Event cancel."""
    from clubledger.events.service import cancel_event

    verify_csrf(session, csrf_token)
    with unit_of_work() as conn:
        result = cancel_event(conn, event_id=event_id, actor_id=session.user_id)
    return redirect(
        f"/admin/events?notice=Cancelled%3B+{result.flagged_count}+payments+need+review"
    )


@router.get("/admin/store")
def inventory(
    request: Request, session: Annotated[Session, Depends(require_perm("store.manage"))]
):
    """Handle GET /admin/store. Inventory."""
    conn = connect(get_db_path())
    try:
        return render(
            request,
            "inventory.html",
            variants=conn.execute(
                "SELECT v.*,p.name,p.base_price_paise FROM variants v JOIN products p ON p.id=v.product_id ORDER BY p.id,v.size"
            ).fetchall(),
            orders=conn.execute(
                "SELECT o.*,u.name,u.email FROM merch_orders o JOIN users u ON u.id=o.user_id WHERE o.status='PAID' ORDER BY o.id"
            ).fetchall(),
        )
    finally:
        conn.close()


@router.post("/admin/store/products")
def product_create(
    request: Request,
    session: Annotated[Session, Depends(require_perm("store.manage"))],
    csrf_token: Token,
    name: Annotated[str, Form()],
    description: Annotated[str, Form()],
    price: Annotated[str, Form()],
    stock: Annotated[int, Form()],
    size: Annotated[str, Form()],
):
    """Handle POST /admin/store/products. Product create."""
    verify_csrf(session, csrf_token)
    if not name.strip() or not size.strip() or stock < 0 or stock > 100000:
        raise DomainError("VALIDATION", 422)
    with unit_of_work() as conn:
        now = clock.now()
        product = conn.execute(
            "INSERT INTO products(name,description,base_price_paise,created_at) VALUES(?,?,?,?)",
            (name, description, money(price), now),
        ).lastrowid
        conn.execute(
            "INSERT INTO variants(product_id,sku,size,physical_qty,created_at) VALUES(?,?,?,?,?)",
            (product, f"CL-{product}-{size}", size, stock, now),
        )
    return redirect("/admin/store?notice=Product+created")


@router.post("/admin/store/variants/{variant_id}/restock")
def restock(
    request: Request,
    variant_id: int,
    session: Annotated[Session, Depends(require_perm("store.manage"))],
    csrf_token: Token,
    quantity: Annotated[int, Form()],
):
    """Handle POST /admin/store/variants/{variant_id}/restock. Restock."""
    verify_csrf(session, csrf_token)
    if quantity < 1 or quantity > 10000:
        raise DomainError("VALIDATION", 422)
    with unit_of_work() as conn:
        if (
            conn.execute(
                "UPDATE variants SET physical_qty=physical_qty+? WHERE id=?",
                (quantity, variant_id),
            ).rowcount
            != 1
        ):
            raise DomainError("NOT_FOUND", 404)
    return redirect("/admin/store?notice=Stock+updated")
