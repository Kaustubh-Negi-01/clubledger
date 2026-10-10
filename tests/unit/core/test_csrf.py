"""Tests for CSRF verification per CONTRACT §4.2, AUTH-07."""

import pytest
from starlette.datastructures import Headers
from starlette.requests import Request

from clubledger.core.csrf import (
    COOKIE_PRE_SESSION_CSRF,
    verify_csrf_token,
    verify_pre_session_csrf,
)
from clubledger.core.errors import DomainError


def test_session_csrf_verification() -> None:
    expected = "valid_csrf_token_123"

    # Exact match passes
    verify_csrf_token(expected, "valid_csrf_token_123")

    # Mismatched or missing token raises 403 CSRF_FAILED
    with pytest.raises(DomainError) as exc_info:
        verify_csrf_token(expected, "wrong_token")
    assert exc_info.value.code == "CSRF_FAILED"
    assert exc_info.value.http_status == 403

    with pytest.raises(DomainError) as exc_info_none:
        verify_csrf_token(expected, None)
    assert exc_info_none.value.code == "CSRF_FAILED"


def test_pre_session_csrf_verification() -> None:
    token = "pre_session_token_abc"

    # Request with cookie matching supplied form token
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/login",
        "headers": [(b"cookie", f"{COOKIE_PRE_SESSION_CSRF}={token}".encode())],
    }
    req = Request(scope)

    # Valid match passes
    verify_pre_session_csrf(req, token)

    # Mismatched form token raises 403 CSRF_FAILED
    with pytest.raises(DomainError) as exc_info:
        verify_pre_session_csrf(req, "mismatched_token")
    assert exc_info.value.code == "CSRF_FAILED"
    assert exc_info.value.http_status == 403

    # Missing cookie raises 403 CSRF_FAILED
    no_cookie_scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/login",
        "headers": [],
    }
    req_no_cookie = Request(no_cookie_scope)
    with pytest.raises(DomainError) as exc_info_no_cookie:
        verify_pre_session_csrf(req_no_cookie, token)
    assert exc_info_no_cookie.value.code == "CSRF_FAILED"
