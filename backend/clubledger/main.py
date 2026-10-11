# In plain English: Starts the web application, checks incoming requests, and connects URLs to handlers.
"""Application factory for ClubLedger per BUILD_ORDER.md §1 and CONTRACT.md §13.2."""

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError

from clubledger.api.auth import router as auth_router
from clubledger.api.payments import router as payments_router
from clubledger.config import get_config
from clubledger.core.errors import DomainError
from clubledger.wiring import build_services


from clubledger.paths import STATIC_DIR


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    config = get_config()
    services = build_services()

    app = FastAPI(title="ClubLedger")
    app.state.services = services

    from clubledger.presentation.ui import render
    from clubledger.security.middleware import register_security_middleware

    register_security_middleware(app)

    # Global DomainError handler mapping to HTTP status without leaking internal secrets
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        if "text/html" in request.headers.get("accept", ""):
            if exc.code == "AUTH_REQUIRED" and request.method == "GET":
                return RedirectResponse("/auth/login", status_code=303)
            response = render(
                request,
                "error.html",
                code=exc.code,
                message=exc.message
                or "This action cannot be completed in the current state.",
            )
            response.status_code = exc.http_status
            if hasattr(exc, "retry_after"):
                response.headers["Retry-After"] = str(exc.retry_after)
            return response
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "code": exc.code,
                "message": exc.message,
            },
            headers={"Retry-After": str(exc.retry_after)}
            if hasattr(exc, "retry_after")
            else None,
        )

    @app.get("/health", include_in_schema=False)
    def health():
        from clubledger.core.db import connect
        from clubledger.config import get_db_path

        conn = connect(get_db_path())
        try:
            conn.execute("SELECT 1 FROM terms LIMIT 1").fetchone()
            return {"status": "ok"}
        finally:
            conn.close()

    # Static assets
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        if "text/html" in request.headers.get("accept", ""):
            response = render(
                request,
                "error.html",
                code="VALIDATION",
                message="Check the required fields and enter valid values, then try again.",
            )
            response.status_code = 422
            return response
        return JSONResponse(
            {
                "code": "VALIDATION",
                "message": "Required fields are missing or invalid.",
            },
            status_code=422,
        )

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Core routers (Owner A)
    app.include_router(auth_router)
    app.include_router(payments_router)

    # Genuine required domain routers (B and C)
    from clubledger.api.membership import router as membership_router
    from clubledger.api.events import router as events_router
    from clubledger.api.reports import router as reports_router

    app.include_router(membership_router)
    app.include_router(events_router)
    app.include_router(reports_router)

    from clubledger.api.workspace import router as web_router
    from clubledger.api.expenses import router as expenses_router
    from clubledger.api.tasks import router as tasks_router

    app.include_router(web_router)
    app.include_router(expenses_router)
    app.include_router(tasks_router)

    from clubledger.api.store import router as store_router

    app.include_router(store_router)
    from clubledger.api.comms import router as comms_router

    app.include_router(comms_router)

    from clubledger.api.notifications import router as notifications_router

    app.include_router(notifications_router)

    @app.get("/")
    def index():
        """Handle GET /. Index."""
        return RedirectResponse("/dashboard", status_code=303)

    return app


app = create_app()
