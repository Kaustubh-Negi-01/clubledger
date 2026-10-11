"""Authenticated notification list and CSRF-protected read actions."""

from typing import Annotated
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from clubledger.security.auth import get_current_session, verify_csrf
from clubledger.core.db import unit_of_work
from clubledger.core.types import Session
from clubledger.notifications.service import mark_read, recent_notifications
from clubledger.presentation.ui import render

router = APIRouter()


@router.get("/notifications")
def notification_list(
    request: Request, session: Annotated[Session, Depends(get_current_session)]
):
    with unit_of_work() as conn:
        notices = recent_notifications(conn, session.user_id)
    return render(request, "notifications.html", notifications=notices)


@router.post("/notifications/read")
def read_notifications(
    session: Annotated[Session, Depends(get_current_session)],
    csrf_token: Annotated[str, Form()],
    notification_key: Annotated[str | None, Form()] = None,
):
    verify_csrf(session, csrf_token)
    with unit_of_work() as conn:
        mark_read(conn, session.user_id, notification_key)
    return RedirectResponse("/notifications", status_code=303)
