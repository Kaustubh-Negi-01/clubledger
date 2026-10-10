"""Officer mail status and authenticated scheduled delivery jobs."""

import os
import secrets
from typing import Annotated
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

from clubledger.core.auth import require_perm, verify_csrf
from clubledger.core.types import Session
from clubledger.core.db import unit_of_work
from clubledger.comms.service import send_reminders
from clubledger.comms.delivery import deliver_outbox, Settings, MailConfigurationError
from clubledger.presentation.ui import render

router = APIRouter()


def run_job():
    """Queue currently due reminders, then deliver a bounded batch."""
    try:
        Settings.load()
    except MailConfigurationError:
        return JSONResponse({"status": "not_configured"}, status_code=503)
    with unit_of_work() as conn:
        reminders = send_reminders(conn)
    return {"reminders_queued": reminders, **deliver_outbox()}


@router.get("/internal/cron/mail", include_in_schema=False)
def scheduled_mail(request: Request):
    """Cron has its own bearer boundary; no browser session or query-string keys."""
    secret = os.environ.get("CRON_SECRET", "")
    authorization = request.headers.get("authorization", "")
    if len(secret) < 32 or not secrets.compare_digest(
        authorization, "Bearer " + secret
    ):
        return JSONResponse({"code": "AUTH_REQUIRED"}, status_code=401)
    return run_job()


@router.get("/admin/mail")
def mail_status(
    request: Request,
    session: Annotated[Session, Depends(require_perm("comms.mail_viewer"))],
):
    with unit_of_work() as conn:
        counts = {
            row["status"]: row["total"]
            for row in conn.execute(
                "SELECT status,COUNT(*) AS total FROM mail_outbox GROUP BY status"
            )
        }
        captured = conn.execute(
            "SELECT COUNT(*) FROM mail_capture c JOIN mail_outbox o ON o.id=c.outbox_id WHERE o.status='SENT'"
        ).fetchone()[0]
        counts["SENT"] = counts.get("SENT", 0) - captured
        counts["CAPTURED"] = captured
        rows = conn.execute(
            "SELECT o.id,o.to_email,o.subject,o.kind,o.status,o.attempts,o.last_error,o.processed_at,c.id AS capture_id FROM mail_outbox o LEFT JOIN mail_capture c ON c.outbox_id=o.id ORDER BY o.id DESC LIMIT 100"
        ).fetchall()
        try:
            Settings.load()
            configured = True
        except MailConfigurationError:
            configured = False
        return render(
            request,
            "mail_status.html",
            configured=configured,
            counts=counts,
            messages=rows,
        )


@router.post("/admin/mail/process")
def process_now(
    request: Request,
    session: Annotated[Session, Depends(require_perm("comms.mail_viewer"))],
    csrf_token: Annotated[str, Form()],
):
    verify_csrf(session, csrf_token)
    result = run_job()
    if isinstance(result, JSONResponse):
        return RedirectResponse(
            "/admin/mail?notice=Email+provider+is+not+configured", status_code=303
        )
    return RedirectResponse("/admin/mail?notice=Mail+queue+processed", status_code=303)
