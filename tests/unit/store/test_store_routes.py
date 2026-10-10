"""Unit tests for store and merchandise routes per CONTRACT.md §12, STO-01 to STO-09."""

import json
import sqlite3
from fastapi.testclient import TestClient
import pytest

from clubledger.core import clock
from clubledger.core.auth import COOKIE_SESSION, create_session
from clubledger.core.db import apply_migrations, connect
from clubledger.core.types import Payment
from clubledger.main import create_app
from clubledger.store.routes import router as store_router
from clubledger.store.service import fulfill_merch_order, seed_store
import clubledger.store.routes as store_routes


def mock_create_payment(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    purpose: str,
    ref_table: str,
    ref_id: int,
    amount_paise: int,
) -> Payment:
    """Mock payment creation for route tests."""
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
    db_file = tmp_path / "test_store_app.db"
    monkeypatch.setenv("CLUBLEDGER_DB_PATH", str(db_file))
    clock.set_now("2026-10-10T10:00:00Z")

    conn = connect(str(db_file))
    apply_migrations(conn)

    # Seed term
    conn.execute(
        "INSERT INTO terms (id, label, starts_at, ends_at, status, closed_at, created_at) "
        "VALUES (1, 'Term 2026-27', '2026-08-01T00:00:00Z', NULL, 'OPEN', NULL, ?);",
        (clock.now(),),
    )

    # Seed roles and permissions
    conn.execute("INSERT INTO roles (id, code, created_at) VALUES (1, 'admin', ?);", (clock.now(),))
    conn.execute("INSERT INTO roles (id, code, created_at) VALUES (2, 'store_staff', ?);", (clock.now(),))

    conn.execute("INSERT INTO permissions (id, code, created_at) VALUES (1, 'store.pickup', ?);", (clock.now(),))
    conn.execute("INSERT INTO permissions (id, code, created_at) VALUES (2, 'store.manage', ?);", (clock.now(),))

    conn.execute("INSERT INTO role_permissions (role_id, permission_id, created_at) VALUES (2, 1, ?);", (clock.now(),))
    conn.execute("INSERT INTO role_permissions (role_id, permission_id, created_at) VALUES (1, 2, ?);", (clock.now(),))

    # Seed users
    # User 1: Regular customer
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (1, 'alice@test.com', 'Alice Customer', 'hash', 1, ?);",
        (clock.now(),),
    )
    # User 2: Second customer
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (2, 'bob@test.com', 'Bob Other', 'hash', 1, ?);",
        (clock.now(),),
    )
    # User 3: Store staff (store.pickup)
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (3, 'staff@test.com', 'Staff Pickup', 'hash', 1, ?);",
        (clock.now(),),
    )
    conn.execute(
        "INSERT INTO user_roles (user_id, role_id, granted_at, created_at) VALUES (3, 2, ?, ?);",
        (clock.now(), clock.now()),
    )

    # Seed store products
    seed_store(conn)
    conn.close()

    app = create_app()
    client = TestClient(app)
    yield client
    clock.reset()


def _login_user(client: TestClient, user_id: int) -> tuple[str, str]:
    """Helper: create session for user_id, set cookie, and return (session_token, csrf_token)."""
    from clubledger.config import get_db_path

    conn = connect(get_db_path())
    try:
        raw_token, csrf_token = create_session(conn, user_id)
        client.cookies.set(COOKIE_SESSION, raw_token)
        return (raw_token, csrf_token)
    finally:
        conn.close()


def test_get_store_catalog_public(app_client):
    res = app_client.get("/store")
    assert res.status_code == 200
    assert "Official Merchandise" in res.text
    assert "Club Classic Hoodie" in res.text
    assert "₹2500.00" in res.text
    assert "Size S" in res.text
    assert "Size M" in res.text


def test_get_product_detail_public_and_404(app_client):
    # Valid product
    res = app_client.get("/store/1")
    assert res.status_code == 200
    assert "Club Classic Hoodie" in res.text
    assert "Log in" in res.text  # Anonymous user prompted to log in

    # Authenticated user sees form
    _login_user(app_client, 1)
    res_auth = app_client.get("/store/1")
    assert res_auth.status_code == 200
    assert "Reserve &amp; Proceed to Payment" in res_auth.text
    assert 'name="idempotency_key"' in res_auth.text

    # Non-existent product -> 404
    res_404 = app_client.get("/store/999")
    assert res_404.status_code == 404


def test_post_store_reserve_requires_auth(app_client):
    res = app_client.post(
        "/store/reserve",
        data={
            "variant_id": 1,
            "qty": 1,
            "csrf_token": "dummy_csrf",
            "idempotency_key": "idemp_noauth",
        },
    )
    assert res.status_code == 401


def test_post_store_reserve_invalid_csrf_forbidden(app_client):
    _login_user(app_client, 1)
    res = app_client.post(
        "/store/reserve",
        data={
            "variant_id": 1,
            "qty": 1,
            "csrf_token": "bad_csrf",
            "idempotency_key": "idemp_bad_csrf",
        },
    )
    assert res.status_code == 403


def test_post_store_reserve_single_item_redirects_to_pay(app_client):
    _, csrf_tok = _login_user(app_client, 1)

    res = app_client.post(
        "/store/reserve",
        data={
            "variant_id": 1,
            "qty": 2,
            "csrf_token": csrf_tok,
            "idempotency_key": "idemp_route_res1",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"].startswith("/pay/")


def test_post_store_reserve_cart_json_redirects_to_pay(app_client):
    _, csrf_tok = _login_user(app_client, 1)

    cart = [{"variant_id": 1, "qty": 1}, {"variant_id": 2, "qty": 2}]
    res = app_client.post(
        "/store/reserve",
        data={
            "cart_json": json.dumps(cart),
            "csrf_token": csrf_tok,
            "idempotency_key": "idemp_route_json",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"].startswith("/pay/")


def test_post_store_reserve_insufficient_stock_conflict(app_client):
    from clubledger.config import get_db_path

    # Set stock of variant 1 to 0
    conn = connect(get_db_path())
    conn.execute("UPDATE variants SET physical_qty = 0, reserved_qty = 0 WHERE id = 1;")
    conn.commit()
    conn.close()

    _, csrf_tok = _login_user(app_client, 1)
    res = app_client.post(
        "/store/reserve",
        data={
            "variant_id": 1,
            "qty": 1,
            "csrf_token": csrf_tok,
            "idempotency_key": "idemp_route_nostock",
        },
    )
    assert res.status_code == 409
    assert res.json()["code"] == "INSUFFICIENT_STOCK"


def test_get_user_orders_authenticated(app_client):
    _, csrf_tok = _login_user(app_client, 1)

    # Place an order
    app_client.post(
        "/store/reserve",
        data={
            "variant_id": 2,
            "qty": 1,
            "csrf_token": csrf_tok,
            "idempotency_key": "idemp_view_orders",
        },
        follow_redirects=False,
    )

    res = app_client.get("/me/orders")
    assert res.status_code == 200
    assert "Your Orders" in res.text
    assert "RESERVED" in res.text
    assert "Club Classic Hoodie" in res.text
    assert "<td>M</td>" in res.text


def test_post_cancel_order_by_owner(app_client):
    from clubledger.config import get_db_path

    _, csrf_tok = _login_user(app_client, 1)

    # Place an order
    app_client.post(
        "/store/reserve",
        data={
            "variant_id": 2,
            "qty": 1,
            "csrf_token": csrf_tok,
            "idempotency_key": "idemp_cancel_route",
        },
        follow_redirects=False,
    )

    conn = connect(get_db_path())
    order_row = conn.execute("SELECT id, status FROM merch_orders WHERE user_id = 1;").fetchone()
    conn.close()
    assert order_row["status"] == "RESERVED"

    # Owner cancels order
    res = app_client.post(
        f"/store/orders/{order_row['id']}/cancel",
        data={"csrf_token": csrf_tok},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"] == "/me/orders"

    conn = connect(get_db_path())
    order_after = conn.execute("SELECT status FROM merch_orders WHERE id = ?;", (order_row["id"],)).fetchone()
    conn.close()
    assert order_after["status"] == "CANCELLED"


def test_post_cancel_order_forbidden_for_other_user(app_client):
    from clubledger.config import get_db_path

    # User 1 places an order
    _, csrf1 = _login_user(app_client, 1)
    app_client.post(
        "/store/reserve",
        data={
            "variant_id": 2,
            "qty": 1,
            "csrf_token": csrf1,
            "idempotency_key": "idemp_other_user",
        },
        follow_redirects=False,
    )

    conn = connect(get_db_path())
    order_row = conn.execute("SELECT id FROM merch_orders WHERE user_id = 1;").fetchone()
    conn.close()

    # User 2 logs in and attempts to cancel User 1's order
    _, csrf2 = _login_user(app_client, 2)
    res = app_client.post(
        f"/store/orders/{order_row['id']}/cancel",
        data={"csrf_token": csrf2},
    )
    assert res.status_code == 403


def test_post_order_pickup_staff_permission(app_client):
    from clubledger.config import get_db_path

    # Customer 1 places order and pays
    _, csrf1 = _login_user(app_client, 1)
    app_client.post(
        "/store/reserve",
        data={
            "variant_id": 1,
            "qty": 2,
            "csrf_token": csrf1,
            "idempotency_key": "idemp_pickup_route",
        },
        follow_redirects=False,
    )

    conn = connect(get_db_path())
    order_row = conn.execute("SELECT id, payment_id FROM merch_orders WHERE user_id = 1;").fetchone()
    p_row = conn.execute("SELECT * FROM payments WHERE id = ?;", (order_row["payment_id"],)).fetchone()
    payment_obj = Payment(
        id=p_row["id"],
        public_id=p_row["public_id"],
        user_id=p_row["user_id"],
        purpose=p_row["purpose"],
        ref_table=p_row["ref_table"],
        ref_id=p_row["ref_id"],
        amount_paise=p_row["amount_paise"],
        status=p_row["status"],
        fulfillment=p_row["fulfillment"],
        term_id=p_row["term_id"],
    )
    fulfill_merch_order(conn, payment_obj, manual=False, now="2026-10-10T10:05:00Z")
    conn.commit()
    conn.close()

    # Customer 1 tries staff pickup -> 403 Forbidden
    res_cust = app_client.post(
        f"/admin/store/orders/{order_row['id']}/pickup",
        data={"csrf_token": csrf1},
    )
    assert res_cust.status_code == 403

    # Staff user (User 3 with store.pickup permission) logs in and marks pickup
    _, csrf_staff = _login_user(app_client, 3)
    res_staff = app_client.post(
        f"/admin/store/orders/{order_row['id']}/pickup",
        data={"csrf_token": csrf_staff},
        follow_redirects=False,
    )
    assert res_staff.status_code == 303

    # Verify order is marked PICKED_UP
    conn = connect(get_db_path())
    o_after = conn.execute("SELECT status, picked_up_by FROM merch_orders WHERE id = ?;", (order_row["id"],)).fetchone()
    conn.close()
    assert o_after["status"] == "PICKED_UP"
    assert o_after["picked_up_by"] == 3
