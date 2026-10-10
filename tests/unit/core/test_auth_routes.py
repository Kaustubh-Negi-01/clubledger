"""HTTP endpoint tests for authentication routes and middleware."""

from pathlib import Path
import pytest
from starlette.testclient import TestClient

from clubledger.core import clock
from clubledger.core.auth import COOKIE_SESSION
from clubledger.core.csrf import COOKIE_PRE_SESSION_CSRF
from clubledger.core.db import apply_migrations, connect
from clubledger.core.ratelimit import reset_rate_limits
from clubledger.main import create_app
from clubledger.seed import seed_roles_and_permissions


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CLUBLEDGER_ENV", "test")
    db_file = tmp_path / "test_routes.db"
    monkeypatch.setenv("CLUBLEDGER_DB_PATH", str(db_file))
    clock.reset()
    reset_rate_limits()

    conn = connect(str(db_file))
    apply_migrations(conn)
    seed_roles_and_permissions(conn)
    conn.close()

    yield
    clock.reset()
    reset_rate_limits()


def test_auth_registration_and_login_flow() -> None:
    app = create_app()
    client = TestClient(app)

    # 1. GET /auth/register sets pre-session CSRF cookie
    reg_page = client.get("/auth/register")
    assert reg_page.status_code == 200
    assert COOKIE_PRE_SESSION_CSRF in reg_page.cookies
    csrf_token = reg_page.cookies[COOKIE_PRE_SESSION_CSRF]

    # 2. POST /auth/register with valid CSRF succeeds and redirects to login
    reg_resp = client.post(
        "/auth/register",
        data={
            "email": "student@skyline.edu",
            "name": "Skyline Student",
            "password": "SecurePassword123",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert reg_resp.status_code == 303
    assert reg_resp.headers["location"] == "/auth/login"

    # 3. Duplicate registration yields 422 VALIDATION (AUTH-01)
    dup_resp = client.post(
        "/auth/register",
        data={
            "email": "STUDENT@skyline.edu",
            "name": "Another Name",
            "password": "SecurePassword123",
            "csrf_token": csrf_token,
        },
        headers={"Accept": "application/json"},
    )
    assert dup_resp.status_code == 422
    assert dup_resp.json()["code"] == "VALIDATION"

    # 4. GET /auth/login sets or preserves pre-session CSRF
    login_page = client.get("/auth/login")
    assert login_page.status_code == 200
    login_csrf = login_page.cookies.get(COOKIE_PRE_SESSION_CSRF, csrf_token)

    # 5. POST /auth/login with wrong password yields 401 (AUTH-02)
    bad_login = client.post(
        "/auth/login",
        data={
            "email": "student@skyline.edu",
            "password": "WrongPassword",
            "csrf_token": login_csrf,
        },
        headers={"Accept": "application/json"},
    )
    assert bad_login.status_code == 401
    assert bad_login.json()["code"] == "AUTH_REQUIRED"

    # 6. POST /auth/login with valid password succeeds and sets session cookie
    good_login = client.post(
        "/auth/login",
        data={
            "email": "student@skyline.edu",
            "password": "SecurePassword123",
            "csrf_token": login_csrf,
        },
        follow_redirects=False,
    )
    assert good_login.status_code == 303
    assert COOKIE_SESSION in good_login.cookies
    session_cookie = good_login.cookies[COOKIE_SESSION]

    # 7. GET /me with session cookie shows user profile (AUTH-01)
    me_resp = client.get("/me", headers={"Accept": "application/json"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["user"]["email"] == "student@skyline.edu"
    assert me_data["user"]["name"] == "Skyline Student"
    assert me_data["membership"] is None
    session_csrf = me_data["csrf_token"]

    # 8. POST /auth/logout invalidates session server-side (AUTH-04)
    logout_resp = client.post(
        "/auth/logout",
        data={"csrf_token": session_csrf},
        follow_redirects=False,
    )
    assert logout_resp.status_code == 303

    # 9. Replaying old session cookie yields 401 (AUTH-04)
    client.cookies.set(COOKIE_SESSION, session_cookie)
    replay_resp = client.get("/me", headers={"Accept": "application/json"})
    assert replay_resp.status_code == 401


def test_csrf_protection_on_mutating_routes() -> None:
    app = create_app()
    client = TestClient(app)

    # Missing pre-session CSRF on register returns 403 CSRF_FAILED (AUTH-07)
    res = client.post(
        "/auth/register",
        data={
            "email": "nocsrf@example.com",
            "name": "No CSRF",
            "password": "Password123",
            "csrf_token": "invalid_or_missing",
        },
        headers={"Accept": "application/json"},
    )
    assert res.status_code == 403
    assert res.json()["code"] == "CSRF_FAILED"


def test_login_rate_limiting_over_http() -> None:
    app = create_app()
    client = TestClient(app)

    # Fetch login page for pre-session CSRF
    login_page = client.get("/auth/login")
    csrf_token = login_page.cookies[COOKIE_PRE_SESSION_CSRF]

    # Register user
    client.post(
        "/auth/register",
        data={"email": "rl@example.com", "name": "RL", "password": "Password123", "csrf_token": csrf_token},
    )

    # 5 attempts allowed within 1 minute
    for _ in range(5):
        client.post(
            "/auth/login",
            data={"email": "rl@example.com", "password": "WrongPassword", "csrf_token": csrf_token},
        )

    # 6th attempt within the minute returns 429 RATE_LIMITED (AUTH-12)
    throttled = client.post(
        "/auth/login",
        data={"email": "rl@example.com", "password": "WrongPassword", "csrf_token": csrf_token},
        headers={"Accept": "application/json"},
    )
    assert throttled.status_code == 429
    assert throttled.json()["code"] == "RATE_LIMITED"
