"""Application factory for ClubLedger per BUILD_ORDER.md §1 and CONTRACT.md §13.2."""

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from clubledger.auth.routes import router as auth_router
from clubledger.payments.routes import router as payments_router
from clubledger.config import get_config
from clubledger.core.errors import DomainError
from clubledger.wiring import build_services


STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    config = get_config()
    services = build_services()

    app = FastAPI(title="ClubLedger")
    app.state.services = services

    # Global DomainError handler mapping to HTTP status without leaking internal secrets
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "code": exc.code,
                "message": exc.message,
            },
        )

    # Static assets
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Core routers (Owner A)
    app.include_router(auth_router)
    app.include_router(payments_router)

    # Mount optional routers from B and C if available
    try:
        from clubledger.membership.routes import router as membership_router
        app.include_router(membership_router)
    except (ImportError, AttributeError):
        pass

    try:
        from clubledger.events.routes import router as events_router
        app.include_router(events_router)
    except (ImportError, AttributeError):
        pass

    try:
        from clubledger.store.routes import router as store_router
        app.include_router(store_router)
    except (ImportError, AttributeError):
        pass

    try:
        from clubledger.reports.routes import router as reports_router
        app.include_router(reports_router)
    except (ImportError, AttributeError):
        pass

    @app.get("/")
    def index():
        return {"app": "ClubLedger", "env": config.env}

    return app


app = create_app()
