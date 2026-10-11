"""Apply sign-in, CSRF, body limits and browser response protections."""

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse


def register_security_middleware(app):
    """Register existing request protections without changing their behavior."""
    from clubledger.presentation.ui import viewer
    from clubledger.security.csrf import (
        ensure_pre_session_csrf,
        COOKIE_PRE_SESSION_CSRF,
    )
    from fastapi import Response

    @app.middleware("http")
    async def page_context(request: Request, call_next):
        # Assets need no account lookup; webhooks use their separate signature check.
        if request.url.path.startswith("/static/") or request.url.path == "/health":
            return await call_next(request)
        if request.url.path == "/webhooks/payments":
            return await call_next(request)
        if request.url.path == "/internal/cron/mail":
            # The cron handler authenticates its own server-only bearer secret.
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response
        request.state.ui = viewer(request)
        # Club content requires a valid session even when a domain route also
        # supports public browsing. Auth forms and email opt-out links remain open.
        public_page = request.url.path in (
            "/auth/login",
            "/auth/register",
            "/subscribe",
        ) or request.url.path.startswith("/unsubscribe/")
        if (
            request.method in ("GET", "HEAD")
            and not public_page
            and not request.state.ui["user"]
        ):
            if "application/json" in request.headers.get("accept", ""):
                return JSONResponse(
                    {"code": "AUTH_REQUIRED", "message": "Sign in to continue."},
                    status_code=401,
                    headers={"Cache-Control": "no-store"},
                )
            return RedirectResponse(
                "/auth/login", status_code=303, headers={"Cache-Control": "no-store"}
            )
        # Page templates receive account data here, rather than querying SQLite.
        cookie_response = Response()
        request.state.pre_csrf = ensure_pre_session_csrf(request, cookie_response)
        if request.method in ("POST", "PATCH", "PUT", "DELETE"):
            # All browser writes need the correct session or pre-login CSRF token.
            import secrets

            public_mutation = request.url.path in (
                "/auth/login",
                "/auth/register",
                "/subscribe",
            ) or request.url.path.startswith("/unsubscribe/")
            if not public_mutation and not request.state.ui["user"]:
                return JSONResponse(
                    {"code": "AUTH_REQUIRED", "message": "Sign in to continue."},
                    status_code=401,
                )
            try:
                if int(request.headers.get("content-length", "0")) > 6 * 1024 * 1024:
                    return JSONResponse(
                        {
                            "code": "UPLOAD_REJECTED",
                            "message": "Request exceeds the upload limit.",
                        },
                        status_code=413,
                    )
                body = await request.body()
                # Bound the actual body as well as the declared Content-Length.
                if len(body) > 6 * 1024 * 1024:
                    return JSONResponse(
                        {
                            "code": "UPLOAD_REJECTED",
                            "message": "Request exceeds the upload limit.",
                        },
                        status_code=413,
                    )
                form = await request.form()
                supplied = request.headers.get("x-csrf-token") or form.get("csrf_token")
                expected = (
                    request.cookies.get(COOKIE_PRE_SESSION_CSRF)
                    if public_mutation
                    else request.state.ui["csrf"]
                )
                if (
                    not expected
                    or not isinstance(supplied, str)
                    or not secrets.compare_digest(expected, supplied)
                ):
                    return JSONResponse(
                        {
                            "code": "CSRF_FAILED",
                            "message": "Refresh the page and try again.",
                        },
                        status_code=403,
                    )
            except (ValueError, TypeError):
                return JSONResponse(
                    {"code": "VALIDATION", "message": "Invalid request body."},
                    status_code=422,
                )
        response = await call_next(request)
        # Copy only cookies, never a provisional Content-Length.
        if not any(
            COOKIE_PRE_SESSION_CSRF + "=" in value
            for value in response.headers.getlist("set-cookie")
        ):
            for value in cookie_response.headers.getlist("set-cookie"):
                response.headers.append("set-cookie", value)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        return response
