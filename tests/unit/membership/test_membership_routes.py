import sqlite3
from fastapi.testclient import TestClient
import pytest

from clubledger.config import get_config
from clubledger.core import clock
from clubledger.core.auth import COOKIE_SESSION, create_session
from clubledger.core.db import apply_migrations, connect
from clubledger.main import create_app
from clubledger.membership.routes import router as membership_router
from clubledger.membership.service import fulfill_dues, seed_plans, start_join
from clubledger.membership.service import _genuine_create_payment
import clubledger.membership.service as membership_service
from clubledger.core.types import Payment


def mock_create_payment(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    purpose: str,
    ref_table: str,
    ref_id: int,
    amount_paise: int,
) -> Payment:
    term_row = conn.execute("SELECT id FROM terms WHERE status = 'OPEN' LIMIT 1;").fetchone()
    term_id = term_row["id"] if term_row else 1
    cur = conn.execute(
        "INSERT INTO payments (public_id, user_id, purpose, ref_table, ref_id, amount_paise, currency, status, fulfillment, term_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'INR', 'CREATED', 'NONE', ?, ?);",
        (f"pay_pub_{ref_id}", user_id, purpose, ref_table, ref_id, amount_paise, term_id, clock.now()),
    )
    return Payment(
        id=cur.lastrowid,  # type: ignore
        public_id=f"pay_pub_{ref_id}",
        user_id=user_id,
        purpose=purpose,
        ref_table=ref_table,
        ref_id=ref_id,
        amount_paise=amount_paise,
        status="CREATED",
        fulfillment="NONE",
        term_id=term_id,
    )


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("CLUBLEDGER_ENV", "test")
    db_file = tmp_path / "test_app.db"
    monkeypatch.setenv("CLUBLEDGER_DB_PATH", str(db_file))
    clock.set_now("2026-10-10T10:00:00Z")

    conn = connect(str(db_file))
    apply_migrations(conn)
    # Seed roles and admin
    conn.execute(
        "INSERT INTO terms (id, label, starts_at, ends_at, status, closed_at, created_at) "
        "VALUES (1, 'Term 2026-27', '2026-08-01T00:00:00Z', NULL, 'OPEN', NULL, ?);",
        (clock.now(),),
    )
    conn.execute(
        "INSERT INTO roles (id, code, created_at) VALUES (1, 'admin', ?);",
        (clock.now(),),
    )
    conn.execute(
        "INSERT INTO roles (id, code, created_at) VALUES (2, 'verifier', ?);",
        (clock.now(),),
    )
    conn.execute(
        "INSERT INTO permissions (id, code, created_at) VALUES (1, 'members.verify', ?);",
        (clock.now(),),
    )
    conn.execute(
        "INSERT INTO role_permissions (role_id, permission_id, created_at) VALUES (2, 1, ?);",
        (clock.now(),),
    )
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (1, 'member@test.com', 'Regular User', 'hash', 1, ?);",
        (clock.now(),),
    )
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (2, 'staff@test.com', 'Staff User', 'hash', 1, ?);",
        (clock.now(),),
    )
    conn.execute(
        "INSERT INTO user_roles (user_id, role_id, granted_at, created_at) "
        "VALUES (2, 2, ?, ?);",
        (clock.now(), clock.now()),
    )
    seed_plans(conn)
    conn.close()

    app = create_app()
    app.include_router(membership_router)

    client = TestClient(app)
    yield client
    clock.reset()


def test_join_get_requires_auth(app_client):
    res = app_client.get("/join")
    assert res.status_code == 401


def test_join_get_with_auth(app_client, monkeypatch):
    from clubledger.config import get_db_path
    conn = connect(get_db_path())
    raw_token, csrf_token = create_session(conn, 1)
    conn.close()

    app_client.cookies.set(COOKIE_SESSION, raw_token)
    res = app_client.get("/join")
    assert res.status_code == 200
    assert "Become a Member" in res.text
    assert "Standard Plan" in res.text or "Member" in res.text


def test_join_post_redirects_to_pay(app_client, monkeypatch):
    # Patch create_payment for isolated testing
    monkeypatch.setattr(membership_service, "_genuine_create_payment", mock_create_payment)

    from clubledger.config import get_db_path
    conn = connect(get_db_path())
    raw_token, csrf_token = create_session(conn, 1)
    conn.close()

    app_client.cookies.set(COOKIE_SESSION, raw_token)
    res = app_client.post(
        "/join",
        data={
            "plan_id": 1,
            "idempotency_key": "test_idemp_key_1",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"].startswith("/pay/pay_pub_")


def test_member_card_get(app_client, monkeypatch):
    monkeypatch.setattr(membership_service, "_genuine_create_payment", mock_create_payment)
    from clubledger.config import get_db_path
    conn = connect(get_db_path())
    raw_token, csrf_token = create_session(conn, 1)

    pay = start_join(conn, 1, 1, "card_idemp_key", create_payment_fn=mock_create_payment)
    fulfill_dues(conn, pay, manual=False, now=clock.now())
    conn.close()

    app_client.cookies.set(COOKIE_SESSION, raw_token)
    res = app_client.get("/members/card")
    assert res.status_code == 200
    assert "Digital Membership Card" in res.text
    assert "ACTIVE" in res.text


def test_verify_staff_permission(app_client, monkeypatch):
    from clubledger.config import get_db_path
    conn = connect(get_db_path())
    # User 1 (no verifier role) -> 403
    raw_token_user, _ = create_session(conn, 1)
    # User 2 (verifier role) -> 200
    raw_token_staff, csrf_staff = create_session(conn, 2)
    conn.close()

    # User 1 forbidden
    app_client.cookies.set(COOKIE_SESSION, raw_token_user)
    res_forbidden = app_client.get("/verify")
    assert res_forbidden.status_code == 403

    # Staff allowed
    app_client.cookies.set(COOKIE_SESSION, raw_token_staff)
    res_ok = app_client.get("/verify")
    assert res_ok.status_code == 200
    assert "Staff Member Verification" in res_ok.text
