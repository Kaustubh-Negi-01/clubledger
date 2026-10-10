"""Authentication endpoints per CONTRACT.md §12."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Header, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from clubledger.config import get_db_path, get_env
from clubledger.core.auth import (
    COOKIE_SESSION,
    authenticate_user,
    create_session,
    get_current_session,
    load_session,
    register_user,
    revoke_session,
)
from clubledger.core.csrf import (
    COOKIE_PRE_SESSION_CSRF,
    ensure_pre_session_csrf,
    verify_csrf_token,
    verify_pre_session_csrf,
)
from clubledger.core.db import connect, unit_of_work
from clubledger.core.errors import DomainError
from clubledger.core.ratelimit import enforce_rate_limit
from clubledger.core.types import Session


router = APIRouter(tags=["auth"])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _get_client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


@router.get("/auth/register", response_class=HTMLResponse)
def get_register(request: Request) -> Response:
    response = templates.TemplateResponse(
        request=request,
        name="auth/register.html",
        context={"csrf_token": ""},
    )
    csrf_token = ensure_pre_session_csrf(request, response)
    # Re-render context with the ensured CSRF token
    return templates.TemplateResponse(
        request=request,
        name="auth/register.html",
        context={"csrf_token": csrf_token},
        headers={key: value for key, value in response.headers.items() if key != "content-length"},
    )


@router.post("/auth/register")
async def post_register(
    request: Request,
    email: Annotated[str, Form(...)],
    name: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    csrf_token: Annotated[str, Form(...)],
) -> Response:
    client_ip = _get_client_ip(request)
    # Rate limit: 10 per hour per IP (AUTH-12)
    enforce_rate_limit(f"register:{client_ip}", limit=10, window_seconds=3600)

    # Verify pre-session CSRF
    verify_pre_session_csrf(request, csrf_token)

    with unit_of_work() as conn:
        register_user(conn, email=email, name=name, password=password)

    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"status": "ok", "email": email})
    return RedirectResponse(url="/auth/login", status_code=303)


@router.get("/auth/login", response_class=HTMLResponse)
def get_login(request: Request) -> Response:
    response = templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={"csrf_token": ""},
    )
    csrf_token = ensure_pre_session_csrf(request, response)
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={"csrf_token": csrf_token},
        headers={key: value for key, value in response.headers.items() if key != "content-length"},
    )


@router.post("/auth/login")
async def post_login(
    request: Request,
    email: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    csrf_token: Annotated[str, Form(...)],
) -> Response:
    client_ip = _get_client_ip(request)
    normalized_email = email.strip().lower()

    # Rate limit: 5 per minute per (IP, email) (AUTH-12)
    enforce_rate_limit(f"login:{client_ip}:{normalized_email}", limit=5, window_seconds=60)

    # Verify pre-session CSRF
    verify_pre_session_csrf(request, csrf_token)

    with unit_of_work() as conn:
        user_id = authenticate_user(conn, email=email, password=password)
        if not user_id:
            raise DomainError("AUTH_REQUIRED", 401, "Invalid email or password")
        raw_token, session_csrf = create_session(conn, user_id)

    is_prod = get_env() == "prod"
    if "application/json" in request.headers.get("accept", ""):
        response = JSONResponse({"status": "ok", "user_id": user_id, "csrf_token": session_csrf})
    else:
        response = RedirectResponse(url="/me", status_code=303)

    response.set_cookie(
        key=COOKIE_SESSION,
        value=raw_token,
        httponly=True,
        samesite="lax",
        secure=is_prod,
        path="/",
    )
    return response


@router.post("/auth/logout")
async def post_logout(
    request: Request,
    csrf_token: Annotated[str | None, Form()] = None,
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    session: Session = Depends(get_current_session),
) -> Response:
    # Mutating route requires CSRF (AUTH-07)
    token_to_verify = csrf_token or x_csrf_token
    verify_csrf_token(session.csrf_token, token_to_verify)

    with unit_of_work() as conn:
        revoke_session(conn, session.id)

    if "application/json" in request.headers.get("accept", ""):
        response = JSONResponse({"status": "ok"})
    else:
        response = RedirectResponse(url="/auth/login", status_code=303)

    response.delete_cookie(key=COOKIE_SESSION, path="/")
    return response


@router.get("/me")
def get_me(
    request: Request,
    session: Session = Depends(get_current_session),
) -> Response:
    conn = connect(get_db_path())
    try:
        user = conn.execute(
            "SELECT id, email, name FROM users WHERE id = ?;", (session.user_id,)
        ).fetchone()
        if not user:
            raise DomainError("NOT_FOUND", 404, "User not found")

        # In H0-H2, no active membership exists for fresh user (AUTH-01)
        from dataclasses import asdict
        from clubledger.core.pricing import active_membership
        from clubledger.core import clock
        membership = active_membership(conn, session.user_id, clock.now())
        data = {
            "user": {"id": user["id"], "email": user["email"], "name": user["name"]},
            "membership": asdict(membership) if membership else None,
            "csrf_token": session.csrf_token,
        }

        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse(data)

        from clubledger.web.routes import dashboard
        return dashboard(request, session)
    finally:
        conn.close()
