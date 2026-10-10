"""Application factory for ClubLedger per BUILD_ORDER.md §1."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from clubledger.auth.routes import router as auth_router
from clubledger.config import get_config
from clubledger.core.errors import DomainError


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    config = get_config()
    app = FastAPI(title="ClubLedger")

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

    # Mount auth router
    app.include_router(auth_router)

    @app.get("/")
    def index():
        return {"app": "ClubLedger", "env": config.env}

    return app


app = create_app()
