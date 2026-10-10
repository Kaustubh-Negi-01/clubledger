"""HTTP route tests for payment checkout, simulator, webhooks, and admin endpoints."""

from pathlib import Path
import json
import pytest
from starlette.testclient import TestClient

from clubledger.config import get_sim_secret
from clubledger.core import clock
from clubledger.core.auth import COOKIE_SESSION, create_session, register_user
from clubledger.core.db import apply_migrations, connect, unit_of_work
from clubledger.core.ratelimit import reset_rate_limits
from clubledger.main import create_app
from clubledger.payments.service import create_payment
from clubledger.payments.simulator import sign_simulator_payload
from clubledger.seed import seed_roles_and_permissions


@pytest.fixture(autouse=True)
def setup_routes_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CLUBLEDGER_ENV", "test")
    db_file = tmp_path / "test_payments_routes.db"
    monkeypatch.setenv("CLUBLEDGER_DB_PATH", str(db_file))
    clock.reset()
    reset_rate_limits()

    conn = connect(str(db_file))
    apply_migrations(conn)
    seed_roles_and_permissions(conn)

    # Insert open term
    conn.execute(
        "INSERT INTO terms (id, label, starts_at, ends_at, status, created_at) "
        "VALUES (1, '2026-Fall', '2026-08-01T00:00:00Z', NULL, 'OPEN', '2026-08-01T00:00:00Z');"
    )

    # Register user 1
    u1_id = register_user(conn, "user1@skyline.edu", "User One", "Password123")
    # Register user 2
    u2_id = register_user(conn, "user2@skyline.edu", "User Two", "Password123")

    # Create payment for user 1
    p = create_payment(
        conn,
        user_id=u1_id,
        purpose="DUES",
        ref_table="memberships",
        ref_id=1,
        amount_paise=25000,
    )

    conn.commit()
    conn.close()

    yield str(db_file), p.public_id, u1_id, u2_id
    clock.reset()
    reset_rate_limits()


def test_get_pay_route_auth_and_ownership(setup_routes_db):
    db_path, public_id, u1_id, u2_id = setup_routes_db
    app = create_app()
    client = TestClient(app)

    # 1. Unauthenticated -> 401
    resp_unauth = client.get(
        f"/pay/{public_id}", headers={"Accept": "application/json"}
    )
    assert resp_unauth.status_code == 401

    # 2. Authenticated foreign user -> 404 (CONTRACT §4.2)
    with unit_of_work(db_path) as conn:
        token2, csrf2 = create_session(conn, u2_id)

    client.cookies.set(COOKIE_SESSION, token2)
    resp_foreign = client.get(f"/pay/{public_id}")
    assert resp_foreign.status_code == 404

    # 3. Authenticated owner -> 200, status becomes PENDING
    with unit_of_work(db_path) as conn:
        token1, csrf1 = create_session(conn, u1_id)

    client.cookies.set(COOKIE_SESSION, token1)
    resp_owner = client.get(f"/pay/{public_id}")
    assert resp_owner.status_code == 200
    assert "simulated payment gateway" in resp_owner.text.lower()

    # Check status changed from CREATED to PENDING
    conn = connect(db_path)
    status = conn.execute(
        "SELECT status FROM payments WHERE public_id = ?;", (public_id,)
    ).fetchone()["status"]
    conn.close()
    assert status == "PENDING"


def test_post_pay_outcome_simulator_flow(setup_routes_db):
    db_path, public_id, u1_id, u2_id = setup_routes_db
    app = create_app()
    client = TestClient(app)

    with unit_of_work(db_path) as conn:
        token1, csrf1 = create_session(conn, u1_id)

    client.cookies.set(COOKIE_SESSION, token1)

    # 1. Missing CSRF -> 403 CSRF_FAILED
    bad_csrf = client.post(
        f"/pay/{public_id}/outcome",
        data={"outcome": "success", "csrf_token": "wrong_csrf"},
        headers={"Accept": "application/json"},
    )
    assert bad_csrf.status_code == 403
    assert bad_csrf.json()["code"] == "CSRF_FAILED"

    # 2. Valid CSRF and outcome=success -> 200 (or redirect)
    good_resp = client.post(
        f"/pay/{public_id}/outcome",
        data={"outcome": "success", "csrf_token": csrf1},
        headers={"Accept": "application/json"},
    )
    assert good_resp.status_code == 200
    assert good_resp.json()["status"] == "ok"
    assert good_resp.json()["outcome"] in ("APPLIED", "APPLIED_UNFULFILLED")

    # Payment status in DB is SUCCEEDED
    conn = connect(db_path)
    p_status = conn.execute(
        "SELECT status FROM payments WHERE public_id = ?;", (public_id,)
    ).fetchone()["status"]
    conn.close()
    assert p_status == "SUCCEEDED"


def test_webhook_payment_endpoint(setup_routes_db):
    db_path, public_id, u1_id, u2_id = setup_routes_db
    app = create_app()
    client = TestClient(app)
    secret = get_sim_secret()

    payload = {
        "event_id": "evt_webhook_test_1",
        "type": "payment.succeeded",
        "payment_id": public_id,
        "user_id": u1_id,
        "amount_paise": 25000,
        "currency": "INR",
    }
    raw_body, header = sign_simulator_payload(payload, secret=secret)

    # 1. Bad signature -> 400 BAD_SIGNATURE, zero writes
    bad_sig_resp = client.post(
        "/webhooks/payments",
        content=raw_body,
        headers={
            "X-Signature": "t=1,v1=0000000000000000000000000000000000000000000000000000000000000000"
        },
    )
    assert bad_sig_resp.status_code == 400
    assert bad_sig_resp.json()["code"] == "BAD_SIGNATURE"

    # 2. Valid signature -> 200, succeeds without session cookie (CSRF-exempt)
    good_resp = client.post(
        "/webhooks/payments",
        content=raw_body,
        headers={"X-Signature": header},
    )
    assert good_resp.status_code == 200
    assert good_resp.json()["status"] == "ok"


def test_admin_payments_permissions(setup_routes_db):
    db_path, public_id, u1_id, u2_id = setup_routes_db
    app = create_app()
    client = TestClient(app)

    with unit_of_work(db_path) as conn:
        token1, csrf1 = create_session(conn, u1_id)
        # Grant admin role to user 2
        role_id = conn.execute("SELECT id FROM roles WHERE code = 'admin';").fetchone()[
            "id"
        ]
        conn.execute(
            "INSERT INTO user_roles (user_id, role_id, granted_at, created_at) "
            "VALUES (?, ?, '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z');",
            (u2_id, role_id),
        )
        token2, csrf2 = create_session(conn, u2_id)

    # User 1 (plain member) -> 403 FORBIDDEN
    client.cookies.set(COOKIE_SESSION, token1)
    forbidden_resp = client.get(
        "/admin/payments", headers={"Accept": "application/json"}
    )
    assert forbidden_resp.status_code == 403
    assert forbidden_resp.json()["code"] == "FORBIDDEN"

    # User 2 (admin) -> 200
    client.cookies.set(COOKIE_SESSION, token2)
    admin_resp = client.get("/admin/payments", headers={"Accept": "application/json"})
    assert admin_resp.status_code == 200
    assert "payments" in admin_resp.json()


def test_admin_payments_html_view_and_actions(setup_routes_db):
    db_path, public_id, u1_id, u2_id = setup_routes_db
    app = create_app()
    client = TestClient(app)

    with unit_of_work(db_path) as conn:
        role_id = conn.execute("SELECT id FROM roles WHERE code = 'admin';").fetchone()[
            "id"
        ]
        conn.execute(
            "INSERT INTO user_roles (user_id, role_id, granted_at, created_at) "
            "VALUES (?, ?, '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z');",
            (u2_id, role_id),
        )
        token2, csrf2 = create_session(conn, u2_id)

        # Mark payment as SUCCEEDED + UNFULFILLED to appear in problem queue
        conn.execute(
            "UPDATE payments SET status = 'SUCCEEDED', fulfillment = 'UNFULFILLED' WHERE public_id = ?;",
            (public_id,),
        )
        p_row = conn.execute(
            "SELECT id FROM payments WHERE public_id = ?;", (public_id,)
        ).fetchone()
        pid = p_row["id"]

        # Insert unapplied receipt event
        conn.execute(
            """
            INSERT INTO payment_events (
                id, event_id, body_sha256, raw_body, type, payment_id,
                claimed_user_id, claimed_public_id, amount_paise, currency,
                outcome, reason, created_at
            ) VALUES (
                101, 'evt_unapp_1', 'sha', '{}', 'payment.succeeded', NULL,
                99, 'pay_unknown', 5000, 'INR', 'UNAPPLIED_RECEIPT', 'UNKNOWN_PAYMENT', '2026-08-01T10:00:00Z'
            );
            """
        )

    client.cookies.set(COOKIE_SESSION, token2)

    # 1. HTML view of problem queue
    resp_html = client.get("/admin/payments?problem=1")
    assert resp_html.status_code == 200
    assert "Problem Queue" in resp_html.text
    assert public_id in resp_html.text
    assert "evt_unapp_1" in resp_html.text

    # 2. POST refund form action (without JSON Accept -> 303 Redirect)
    ref_resp = client.post(
        f"/admin/payments/{pid}/refund",
        data={"csrf_token": csrf2},
        follow_redirects=False,
    )
    assert ref_resp.status_code == 303
    assert ref_resp.headers["location"] == "/admin/payments?problem=1"

    # 3. POST resolve unapplied receipt (DISMISS with note)
    res_resp = client.post(
        "/admin/payment-events/101/resolve",
        data={"action": "DISMISS", "note": "Spurious receipt", "csrf_token": csrf2},
        follow_redirects=False,
    )
    assert res_resp.status_code == 303
