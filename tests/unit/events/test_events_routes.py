"""Unit tests for events routes per CONTRACT.md §12."""

import sqlite3
from fastapi.testclient import TestClient
import pytest

from clubledger.core import clock
from clubledger.security.auth import COOKIE_SESSION, create_session
from clubledger.core.db import apply_migrations, connect
from clubledger.core.types import Payment
from clubledger.api.events import router as events_router
from clubledger.events.service import fulfill_ticket_hold
import clubledger.events.service as events_service
from clubledger.main import create_app


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
    term_row = conn.execute(
        "SELECT id FROM terms WHERE status = 'OPEN' LIMIT 1;"
    ).fetchone()
    term_id = term_row["id"] if term_row else 1
    cur = conn.execute(
        "INSERT INTO payments (public_id, user_id, purpose, ref_table, ref_id, amount_paise, currency, status, fulfillment, term_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'INR', 'CREATED', 'NONE', ?, ?);",
        (
            f"pay_pub_{ref_id}",
            user_id,
            purpose,
            ref_table,
            ref_id,
            amount_paise,
            term_id,
            clock.now(),
        ),
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
    db_file = tmp_path / "test_events_app.db"
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
    conn.execute(
        "INSERT INTO roles (id, code, created_at) VALUES (1, 'admin', ?);",
        (clock.now(),),
    )
    conn.execute(
        "INSERT INTO roles (id, code, created_at) VALUES (2, 'door_staff', ?);",
        (clock.now(),),
    )
    conn.execute(
        "INSERT INTO roles (id, code, created_at) VALUES (3, 'manager', ?);",
        (clock.now(),),
    )

    conn.execute(
        "INSERT INTO permissions (id, code, created_at) VALUES (1, 'events.checkin', ?);",
        (clock.now(),),
    )
    conn.execute(
        "INSERT INTO permissions (id, code, created_at) VALUES (2, 'events.manage', ?);",
        (clock.now(),),
    )

    conn.execute(
        "INSERT INTO role_permissions (role_id, permission_id, created_at) VALUES (2, 1, ?);",
        (clock.now(),),
    )
    conn.execute(
        "INSERT INTO role_permissions (role_id, permission_id, created_at) VALUES (3, 2, ?);",
        (clock.now(),),
    )

    # Seed users
    # User 1: Regular attendee
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (1, 'alice@test.com', 'Alice Attendee', 'hash', 1, ?);",
        (clock.now(),),
    )
    # User 2: Second user (unauthorized for Alice's tickets)
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (2, 'bob@test.com', 'Bob Other', 'hash', 1, ?);",
        (clock.now(),),
    )
    # User 3: Door staff (events.checkin)
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (3, 'staff@test.com', 'Staff Door', 'hash', 1, ?);",
        (clock.now(),),
    )
    conn.execute(
        "INSERT INTO user_roles (user_id, role_id, granted_at, created_at) VALUES (3, 2, ?, ?);",
        (clock.now(), clock.now()),
    )
    # User 4: Event Manager (events.manage)
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (4, 'manager@test.com', 'Event Manager', 'hash', 1, ?);",
        (clock.now(),),
    )
    conn.execute(
        "INSERT INTO user_roles (user_id, role_id, granted_at, created_at) VALUES (4, 3, ?, ?);",
        (clock.now(), clock.now()),
    )

    # Seed Events
    # Event 1: Paid Gala
    conn.execute(
        "INSERT INTO events ("
        "  id, term_id, title, venue, starts_at, ends_at, capacity, "
        "  member_price_paise, public_price_paise, max_per_order, status, created_at"
        ") VALUES (1, 1, 'Annual Gala', 'Grand Hall', '2026-11-01T18:00:00Z', '2026-11-01T22:00:00Z', 50, 50000, 75000, 4, 'ON_SALE', ?);",
        (clock.now(),),
    )
    # Event 2: Free Workshop
    conn.execute(
        "INSERT INTO events ("
        "  id, term_id, title, venue, starts_at, ends_at, capacity, "
        "  member_price_paise, public_price_paise, max_per_order, status, created_at"
        ") VALUES (2, 1, 'Free Coding Jam', 'Lab 101', '2026-11-05T14:00:00Z', '2026-11-05T17:00:00Z', 20, 0, 0, 2, 'ON_SALE', ?);",
        (clock.now(),),
    )
    # Event 3: Draft Gala (hidden)
    conn.execute(
        "INSERT INTO events ("
        "  id, term_id, title, venue, starts_at, ends_at, capacity, "
        "  member_price_paise, public_price_paise, max_per_order, status, created_at"
        ") VALUES (3, 1, 'Secret Gala', 'Hidden Cave', '2026-12-01T18:00:00Z', '2026-12-01T22:00:00Z', 10, 100000, 100000, 1, 'DRAFT', ?);",
        (clock.now(),),
    )

    conn.close()

    app = create_app()
    app.include_router(events_router)

    client = TestClient(app)
    yield client
    clock.reset()


def test_signed_in_events_list(app_client):
    from clubledger.config import get_db_path

    conn = connect(get_db_path())
    token, _ = create_session(conn, 1)
    conn.close()
    app_client.cookies.set(COOKIE_SESSION, token)
    res = app_client.get("/events")
    assert res.status_code == 200
    assert "Annual Gala" in res.text
    assert "Free Coding Jam" in res.text
    # DRAFT event must be hidden per EVT-01
    assert "Secret Gala" not in res.text


def test_signed_in_event_detail(app_client):
    from clubledger.config import get_db_path

    conn = connect(get_db_path())
    token, _ = create_session(conn, 1)
    conn.close()
    app_client.cookies.set(COOKIE_SESSION, token)
    res = app_client.get("/events/1")
    assert res.status_code == 200
    assert "Annual Gala" in res.text
    assert "Grand Hall" in res.text
    assert "Reserve Tickets" in res.text

    # Detail of draft event returns 404
    res_draft = app_client.get("/events/3")
    assert res_draft.status_code == 404

    # Detail of non-existent event returns 404
    res_none = app_client.get("/events/999")
    assert res_none.status_code == 404


def test_event_detail_authenticated_shows_form(app_client):
    from clubledger.config import get_db_path

    conn = connect(get_db_path())
    raw_token, csrf_token = create_session(conn, 1)
    conn.close()

    app_client.cookies.set(COOKIE_SESSION, raw_token)
    res = app_client.get("/events/1")
    assert res.status_code == 200
    assert "Reserve Tickets" in res.text
    assert 'name="idempotency_key"' in res.text
    assert 'name="csrf_token"' in res.text


def test_hold_post_requires_auth(app_client):
    res = app_client.post(
        "/events/1/hold", data={"qty": 1, "idempotency_key": "k", "csrf_token": "c"}
    )
    assert res.status_code == 401


def test_hold_post_free_tickets_redirects_to_ticket(app_client):
    from clubledger.config import get_db_path

    conn = connect(get_db_path())
    raw_token, csrf_token = create_session(conn, 1)
    conn.close()

    app_client.cookies.set(COOKIE_SESSION, raw_token)
    res = app_client.post(
        "/events/2/hold",
        data={
            "qty": 2,
            "idempotency_key": "free_hold_key_1",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"].startswith("/tickets/")


def test_hold_post_paid_tickets_with_missing_dependency(app_client, monkeypatch):
    # Explicitly simulate absence in isolated unit test per TURBO_B.txt
    monkeypatch.setattr(events_service, "_genuine_create_payment", None)
    from clubledger.config import get_db_path

    conn = connect(get_db_path())
    raw_token, csrf_token = create_session(conn, 1)
    conn.close()

    app_client.cookies.set(COOKIE_SESSION, raw_token)
    res = app_client.post(
        "/events/1/hold",
        data={
            "qty": 1,
            "idempotency_key": "paid_hold_blocker_key",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert res.status_code == 503
    assert "DEPENDENCY_BLOCKER" in res.json()["code"]


def test_hold_post_paid_tickets_with_genuine_payment_service(app_client):
    # Now that A's payments module is integrated, genuine payment creation works without mocks
    from clubledger.config import get_db_path

    conn = connect(get_db_path())
    raw_token, csrf_token = create_session(conn, 1)
    conn.close()

    app_client.cookies.set(COOKIE_SESSION, raw_token)
    res = app_client.post(
        "/events/1/hold",
        data={
            "qty": 2,
            "idempotency_key": "paid_hold_key_genuine",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"].startswith("/pay/")


def test_hold_post_paid_tickets_with_mock_payment_redirects_to_pay(
    app_client, monkeypatch
):
    monkeypatch.setattr(events_service, "_genuine_create_payment", mock_create_payment)

    from clubledger.config import get_db_path

    conn = connect(get_db_path())
    raw_token, csrf_token = create_session(conn, 1)
    conn.close()

    app_client.cookies.set(COOKIE_SESSION, raw_token)
    res = app_client.post(
        "/events/1/hold",
        data={
            "qty": 2,
            "idempotency_key": "paid_hold_key_2",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"].startswith("/pay/pay_pub_")


def test_ticket_view_ownership_and_security(app_client, monkeypatch):
    monkeypatch.setattr(events_service, "_genuine_create_payment", mock_create_payment)
    from clubledger.config import get_db_path

    conn = connect(get_db_path())
    raw_token_alice, csrf_alice = create_session(conn, 1)
    raw_token_bob, csrf_bob = create_session(conn, 2)

    # Issue a ticket to Alice
    conn.execute(
        "INSERT INTO ticket_holds (id, event_id, user_id, qty, unit_price_paise, price_tier, status, expires_at, created_at) "
        "VALUES (10, 1, 1, 1, 75000, 'PUBLIC', 'CONSUMED', '2026-10-10T12:00:00Z', '2026-10-10T10:00:00Z');"
    )
    cur_pay = conn.execute(
        "INSERT INTO payments (public_id, user_id, purpose, ref_table, ref_id, amount_paise, currency, status, fulfillment, term_id, created_at) "
        "VALUES ('pay_alice_1', 1, 'TICKET', 'ticket_holds', 10, 75000, 'INR', 'SUCCEEDED', 'FULFILLED', 1, '2026-10-10T10:00:00Z');"
    )
    cur = conn.execute(
        "INSERT INTO tickets (id, event_id, hold_id, seat_index, user_id, payment_id, code, price_paise, price_tier, status, created_at) "
        "VALUES (100, 1, 10, 1, 1, ?, 'TKT-10-1-ABCXYZ', 75000, 'PUBLIC', 'ISSUED', '2026-10-10T10:00:00Z');",
        (cur_pay.lastrowid,),
    )
    ticket_id = cur.lastrowid
    conn.close()

    # Anonymous access -> 401
    app_client.cookies.clear()
    res_anon = app_client.get(
        f"/tickets/{ticket_id}", headers={"Accept": "application/json"}
    )
    assert res_anon.status_code == 401

    # Alice (owner) access -> 200 OK
    app_client.cookies.set(COOKIE_SESSION, raw_token_alice)
    res_alice = app_client.get(f"/tickets/{ticket_id}")
    assert res_alice.status_code == 200
    assert "TKT-10-1-ABCXYZ" in res_alice.text
    assert "Annual Gala" in res_alice.text

    # Bob (non-owner) access -> 403 Forbidden
    app_client.cookies.set(COOKIE_SESSION, raw_token_bob)
    res_bob = app_client.get(f"/tickets/{ticket_id}")
    assert res_bob.status_code == 404


def test_checkin_flow_and_permission(app_client):
    from clubledger.config import get_db_path

    conn = connect(get_db_path())
    raw_token_alice, _ = create_session(conn, 1)
    raw_token_staff, csrf_staff = create_session(conn, 3)

    # Issue a ticket
    conn.execute(
        "INSERT INTO ticket_holds (id, event_id, user_id, qty, unit_price_paise, price_tier, status, expires_at, created_at) "
        "VALUES (20, 1, 1, 1, 50000, 'MEMBER', 'CONSUMED', '2026-10-10T12:00:00Z', '2026-10-10T10:00:00Z');"
    )
    cur_pay = conn.execute(
        "INSERT INTO payments (public_id, user_id, purpose, ref_table, ref_id, amount_paise, currency, status, fulfillment, term_id, created_at) "
        "VALUES ('pay_scan_1', 1, 'TICKET', 'ticket_holds', 20, 50000, 'INR', 'SUCCEEDED', 'FULFILLED', 1, '2026-10-10T10:00:00Z');"
    )
    conn.execute(
        "INSERT INTO tickets (id, event_id, hold_id, seat_index, user_id, payment_id, code, price_paise, price_tier, status, created_at) "
        "VALUES (200, 1, 20, 1, 1, ?, 'TKT-SCAN-CODE', 50000, 'MEMBER', 'ISSUED', '2026-10-10T10:00:00Z');",
        (cur_pay.lastrowid,),
    )
    conn.close()

    # Regular user Alice attempts check-in -> 403
    app_client.cookies.set(COOKIE_SESSION, raw_token_alice)
    res_user_get = app_client.get("/checkin/1")
    assert res_user_get.status_code == 403

    # Staff user gets check-in page -> 200
    app_client.cookies.set(COOKIE_SESSION, raw_token_staff)
    res_staff_get = app_client.get("/checkin/1")
    assert res_staff_get.status_code == 200
    assert "Staff Door Check-In" in res_staff_get.text

    # First scan -> 200 with OK admission granted
    res_scan_1 = app_client.post(
        "/checkin/1/scan",
        data={"code": "TKT-SCAN-CODE", "csrf_token": csrf_staff},
    )
    assert res_scan_1.status_code == 200
    assert "Admission Granted" in res_scan_1.text

    # Second scan -> 409 Conflict with Ticket Already Used and timestamp preserved
    res_scan_2 = app_client.post(
        "/checkin/1/scan",
        data={"code": "TKT-SCAN-CODE", "csrf_token": csrf_staff},
    )
    assert res_scan_2.status_code == 409
    assert "Ticket Already Used" in res_scan_2.text
    assert "already used at" in res_scan_2.text.lower()


def test_hold_post_idempotency_conflict_different_parameters(app_client):
    from clubledger.config import get_db_path

    conn = connect(get_db_path())
    raw_token, csrf_token = create_session(conn, 1)
    conn.close()

    app_client.cookies.set(COOKIE_SESSION, raw_token)
    res1 = app_client.post(
        "/events/2/hold",
        data={
            "qty": 1,
            "idempotency_key": "conflict_test_key",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert res1.status_code == 303

    # Replay with changed qty -> 409 CONFLICT
    res2 = app_client.post(
        "/events/2/hold",
        data={
            "qty": 2,
            "idempotency_key": "conflict_test_key",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert res2.status_code == 422
    assert res2.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_admin_event_report_permission(app_client):
    from clubledger.config import get_db_path

    conn = connect(get_db_path())
    raw_token_user, _ = create_session(conn, 1)
    raw_token_manager, _ = create_session(conn, 4)
    conn.close()

    # User 1 -> 403
    app_client.cookies.set(COOKIE_SESSION, raw_token_user)
    res_unauth = app_client.get("/admin/events/1/report")
    assert res_unauth.status_code == 403

    # Manager -> 200
    app_client.cookies.set(COOKIE_SESSION, raw_token_manager)
    res_auth = app_client.get("/admin/events/1/report")
    assert res_auth.status_code == 200
    # Read the heading as a person does; source indentation is not behavior.
    from bs4 import BeautifulSoup

    headings = BeautifulSoup(res_auth.text, "html.parser").select("h2")
    assert "Attendance & Financial Summary: Annual Gala" in [
        " ".join(heading.get_text(" ", strip=True).split()) for heading in headings
    ]
    assert "Tickets Sold" in res_auth.text
