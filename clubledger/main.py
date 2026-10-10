"""Application factory for ClubLedger per BUILD_ORDER.md §1 and CONTRACT.md §13.2."""

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError

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

    from clubledger.web.ui import viewer, render
    from clubledger.core.csrf import ensure_pre_session_csrf, COOKIE_PRE_SESSION_CSRF
    from fastapi import Response

    @app.middleware('http')
    async def page_context(request: Request, call_next):
        if request.url.path.startswith('/static/'):
            return await call_next(request)
        if request.url.path == '/webhooks/payments':
            return await call_next(request)
        request.state.ui = viewer(request)
        cookie_response = Response()
        request.state.pre_csrf = ensure_pre_session_csrf(request, cookie_response)
        if request.method in ('POST','PATCH','PUT','DELETE'):
            import secrets
            public_mutation = request.url.path in ('/auth/login','/auth/register','/subscribe') or request.url.path.startswith('/unsubscribe/')
            if not public_mutation and not request.state.ui['user']:
                return JSONResponse({'code':'AUTH_REQUIRED','message':'Sign in to continue.'},status_code=401)
            try:
                if int(request.headers.get('content-length','0')) > 6*1024*1024:
                    return JSONResponse({'code':'UPLOAD_REJECTED','message':'Request exceeds the upload limit.'},status_code=413)
                body = await request.body()
                if len(body) > 6*1024*1024:
                    return JSONResponse({'code':'UPLOAD_REJECTED','message':'Request exceeds the upload limit.'},status_code=413)
                form = await request.form()
                supplied = request.headers.get('x-csrf-token') or form.get('csrf_token')
                expected = request.cookies.get(COOKIE_PRE_SESSION_CSRF) if public_mutation else request.state.ui['csrf']
                if not expected or not isinstance(supplied,str) or not secrets.compare_digest(expected,supplied):
                    return JSONResponse({'code':'CSRF_FAILED','message':'Refresh the page and try again.'},status_code=403)
            except (ValueError,TypeError):
                return JSONResponse({'code':'VALIDATION','message':'Invalid request body.'},status_code=422)
        response = await call_next(request)
        # Copy only cookies, never a provisional Content-Length.
        if not any(COOKIE_PRE_SESSION_CSRF+'=' in value for value in response.headers.getlist('set-cookie')):
            for value in cookie_response.headers.getlist('set-cookie'):
                response.headers.append('set-cookie', value)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Cache-Control'] = 'no-store'
        return response

    # Global DomainError handler mapping to HTTP status without leaking internal secrets
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        if 'text/html' in request.headers.get('accept', ''):
            if exc.code == 'AUTH_REQUIRED' and request.method == 'GET':
                return RedirectResponse('/auth/login', status_code=303)
            response = render(request, 'error.html', code=exc.code, message=exc.message or 'This action cannot be completed in the current state.')
            response.status_code = exc.http_status
            if hasattr(exc, 'retry_after'):
                response.headers['Retry-After'] = str(exc.retry_after)
            return response
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "code": exc.code,
                "message": exc.message,
            },
            headers={'Retry-After':str(exc.retry_after)} if hasattr(exc,'retry_after') else None,
        )

    # Static assets
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        if 'text/html' in request.headers.get('accept', ''):
            response = render(request, 'error.html', code='VALIDATION', message='Check the required fields and enter valid values, then try again.')
            response.status_code = 422
            return response
        return JSONResponse({'code':'VALIDATION','message':'Required fields are missing or invalid.'}, status_code=422)

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Core routers (Owner A)
    app.include_router(auth_router)
    app.include_router(payments_router)

    # Genuine required domain routers (B and C)
    from clubledger.membership.routes import router as membership_router
    from clubledger.events.routes import router as events_router
    from clubledger.reports.routes import router as reports_router

    app.include_router(membership_router)
    app.include_router(events_router)
    app.include_router(reports_router)

    from clubledger.web.routes import router as web_router
    from clubledger.expenses.routes import router as expenses_router
    from clubledger.tasks.routes import router as tasks_router
    app.include_router(web_router)
    app.include_router(expenses_router)
    app.include_router(tasks_router)

    from clubledger.store.routes import router as store_router
    app.include_router(store_router)

    @app.get("/")
    def index():
        return RedirectResponse('/dashboard', status_code=303)

    return app


app = create_app()
