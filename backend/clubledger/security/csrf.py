# In plain English: Prevents another website from submitting an action using a logged-in user session.
"""CSRF protection module per CONTRACT.md §4.2, AUTH-07, AUTH-08."""

import secrets
from fastapi import Request, Response

from clubledger.config import get_env
from clubledger.core.errors import DomainError
from clubledger.core.idgen import generate_csrf_token


COOKIE_PRE_SESSION_CSRF = "cl_csrf"


def verify_csrf_token(expected: str, supplied: str | None) -> None:
    """Verify session CSRF token with constant-time comparison."""
    if not supplied or not expected or not secrets.compare_digest(expected, supplied):
        raise DomainError("CSRF_FAILED", 403, "CSRF verification failed")


def get_pre_session_csrf(request: Request) -> str | None:
    """Retrieve pre-session CSRF token from request cookies."""
    return request.cookies.get(COOKIE_PRE_SESSION_CSRF)


def ensure_pre_session_csrf(request: Request, response: Response) -> str:
    """Retrieve or generate a pre-session CSRF token and set it in the response cookie."""
    token = get_pre_session_csrf(request)
    if not token:
        token = generate_csrf_token()
        is_prod = get_env() == "prod"
        response.set_cookie(
            key=COOKIE_PRE_SESSION_CSRF,
            value=token,
            httponly=True,
            samesite="lax",
            secure=is_prod,
            path="/",
        )
    return token


def verify_pre_session_csrf(request: Request, supplied: str | None) -> None:
    """Verify double-submit pre-session CSRF token."""
    expected = get_pre_session_csrf(request)
    if not expected or not supplied or not secrets.compare_digest(expected, supplied):
        raise DomainError("CSRF_FAILED", 403, "Pre-session CSRF verification failed")
