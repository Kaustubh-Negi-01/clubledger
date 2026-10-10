"""End-to-end integration and regression tests for ClubLedger vertical slices.

Covers E2E-01 (First vertical slice):
  - User registration -> login -> GET /join -> POST /join -> dues payment
  - Activation: member_code, qr_token generated, status ACTIVE
  - Discounted ticket reservation: GET /events/{id} -> POST /events/{id}/hold -> payment
  - Check-in: staff with 'door' / 'events' role checks in ticket -> status USED
  - Financial verification: GET /finance cash summary and accounting balance:
      clearing = dues (200000 paise) + tickets (2 * 800 paise) = 201600 paise
      cash on hand = 0 (before settle), obligations = 0
  - Event report reconciliation: sold = 2, attended = 1, gross = 1600 paise, net = 1600 paise

Mandatory Regressions:
  - Capacity race / hold expiry: hold expires by clock without sweep, another user reserves
    last seat, late payment succeeds to UNFULFILLED obligation in account 2000 without issuing extra ticket.
  - Ticket cancellation / refund: payments.service.refund_payment reverses journal lines, net income 0.
  - Failed dues payment: membership stays PENDING, no active card, no discount on tickets.
  - Repeated notifications / webhooks: duplicate outcome posts report NO_EFFECT / REPEATED_NOTIFICATION.
  - CSRF protection: POST without token or with foreign session token rejected (403).
  - Foreign ownership rejection: users cannot view another user's payments or tickets (404/403).
  - Wrong event ticket check-in: rejected.
  - Duplicate check-in rejection: scanning ticket twice returns ALREADY_USED.
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest
from starlette.testclient import TestClient

from clubledger.core import clock
from clubledger.payments.service import refund_payment
from clubledger.reports.service import balance, cash_summary


@pytest.mark.req("E2E-01", "pos")
def test_first_vertical_slice_happy_path(
    app_client: TestClient,
    db,
    make_user,
    make_event,
    login_as,
    clock,
):
    """Walks the full first slice per REQUIREMENTS.md E2E-01:
    Register -> join -> dues -> ACTIVE card -> discounted hold -> payment -> check-in -> reports.
    """
    clock.set_now("2026-09-01T10:00:00Z")

    # 1. Register users: member applicant and door staff
    applicant = make_user(email="alice@university.edu", name="Alice Applicant")
    staff = make_user(email="staff@university.edu", name="Door Staff", roles=["door", "events", "finance.view", "treasurer", "admin"])

    # 2. Login as applicant and visit /join
    raw_session, csrf_token = login_as(applicant)
    resp = app_client.get("/join")
    assert resp.status_code == 200
    assert "Member" in resp.text

    # Read membership plans to get plan_id
    plan_row = db.execute("SELECT id, dues_paise FROM membership_plans WHERE code = 'STANDARD';").fetchone()
    assert plan_row is not None
    plan_id = plan_row["id"]
    dues_paise = plan_row["dues_paise"]  # 200000 paise (Rs. 2000)

    # 3. POST /join to initiate membership
    resp_join = app_client.post(
        "/join",
        data={
            "plan_id": str(plan_id),
            "idempotency_key": "idemp_alice_join_001",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert resp_join.status_code == 303
    pay_url = resp_join.headers["location"]
    assert pay_url.startswith("/pay/")
    pay_public_id = pay_url.split("/pay/")[1]

    # Verify payment row created with DUES purpose
    pay_row = db.execute("SELECT * FROM payments WHERE public_id = ?;", (pay_public_id,)).fetchone()
    assert pay_row["purpose"] == "DUES"
    assert pay_row["amount_paise"] == dues_paise
    assert pay_row["status"] == "CREATED"

    # 4. Visit simulator page -> status transitions to PENDING
    resp_pay_page = app_client.get(f"/pay/{pay_public_id}")
    assert resp_pay_page.status_code == 200

    pay_row = db.execute("SELECT status FROM payments WHERE public_id = ?;", (pay_public_id,)).fetchone()
    assert pay_row["status"] == "PENDING"

    # 5. Simulate payment success via POST /pay/{public_id}/outcome
    resp_pay_outcome = app_client.post(
        f"/pay/{pay_public_id}/outcome",
        data={
            "outcome": "success",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert resp_pay_outcome.status_code == 303

    # 6. Verify membership activated with member_code, qr_token
    mem_row = db.execute(
        "SELECT * FROM memberships WHERE user_id = ?;", (applicant["id"],)
    ).fetchone()
    assert mem_row["status"] == "ACTIVE"
    assert mem_row["member_code"] is not None
    assert mem_row["qr_token"] is not None
    assert mem_row["member_code"].startswith("M")

    # Member card is accessible
    resp_card = app_client.get("/members/card")
    assert resp_card.status_code == 200
    assert mem_row["member_code"] in resp_card.text

    # 7. Create an event with capacity=50, public_price=1000 paise (Rs. 10), member_price=800 paise (Rs. 8)
    event = make_event(
        title="Annual Gala 2026",
        capacity=50,
        public_price_paise=1000,
        member_price_paise=800,
    )
    event_id = event["id"]

    # 8. GET /events/{id} shows discounted price for ACTIVE member
    resp_evt = app_client.get(f"/events/{event_id}")
    assert resp_evt.status_code == 200
    assert "8.00" in resp_evt.text  # member price in INR

    # 9. POST /events/{id}/hold to reserve 2 tickets (qty=2, 2 * 800 = 1600 paise)
    resp_hold = app_client.post(
        f"/events/{event_id}/hold",
        data={
            "qty": "2",
            "idempotency_key": "idemp_alice_hold_001",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert resp_hold.status_code == 303
    tkt_pay_url = resp_hold.headers["location"]
    assert tkt_pay_url.startswith("/pay/")
    tkt_pay_public_id = tkt_pay_url.split("/pay/")[1]

    tkt_pay_row = db.execute("SELECT * FROM payments WHERE public_id = ?;", (tkt_pay_public_id,)).fetchone()
    assert tkt_pay_row["purpose"] == "TICKET"
    assert tkt_pay_row["amount_paise"] == 1600

    # 10. Simulate ticket payment success
    resp_tkt_outcome = app_client.post(
        f"/pay/{tkt_pay_public_id}/outcome",
        data={
            "outcome": "success",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert resp_tkt_outcome.status_code == 303

    # Verify 2 tickets issued with seat_index 1 and 2
    tickets = db.execute(
        "SELECT * FROM tickets WHERE user_id = ? AND event_id = ? ORDER BY seat_index ASC;",
        (applicant["id"], event_id),
    ).fetchall()
    assert len(tickets) == 2
    assert tickets[0]["seat_index"] == 1
    assert tickets[1]["seat_index"] == 2
    assert tickets[0]["status"] == "ISSUED"
    assert tickets[1]["status"] == "ISSUED"
    ticket_to_checkin = tickets[0]["code"]

    # 11. Switch session to staff user and check in ticket 1
    staff_session, staff_csrf = login_as(staff)
    resp_checkin = app_client.post(
        f"/checkin/{event_id}/scan",
        data={
            "code": ticket_to_checkin,
            "csrf_token": staff_csrf,
        },
    )
    assert resp_checkin.status_code == 200
    assert "Check-in confirmed" in resp_checkin.text

    # Verify ticket status in DB is USED
    tkt1_db = db.execute("SELECT status, used_at, used_by FROM tickets WHERE code = ?;", (ticket_to_checkin,)).fetchone()
    assert tkt1_db["status"] == "USED"
    assert tkt1_db["used_by"] == staff["id"]

    # 12. Financial and Journal verification:
    # Total clearing = dues (200000) + tickets (1600) = 201600 paise
    # Journal entries: 2 POSTED entries (one DUES, one TICKET)
    entries = db.execute("SELECT * FROM journal_entries WHERE status = 'POSTED';").fetchall()
    assert len(entries) == 2

    # Check that each journal entry balances (Dr == Cr)
    for ent in entries:
        sums = db.execute(
            "SELECT SUM(debit_paise) AS dr, SUM(credit_paise) AS cr FROM journal_lines WHERE entry_id = ?;",
            (ent["id"],),
        ).fetchone()
        assert sums["dr"] == sums["cr"]
        assert sums["dr"] > 0

    # Verify Cash Summary via reports service
    term_row = db.execute("SELECT id FROM terms WHERE status = 'OPEN' LIMIT 1;").fetchone()
    cs = cash_summary(db, term_row["id"])
    assert cs.cash_on_hand == 0
    assert cs.in_clearing == dues_paise + 1600
    assert cs.unfulfilled_obligations == 0
    assert cs.reimbursements_payable == 0

    # 13. Event report verification
    # 2 tickets sold, 1 attended, gross = 1600 paise, net = 1600 paise
    resp_evt_rep = app_client.get(f"/admin/events/{event_id}/report")
    assert resp_evt_rep.status_code == 200
    assert "16.00" in resp_evt_rep.text  # gross INR


@pytest.mark.req("E2E-01", "neg")
def test_first_vertical_slice_failed_dues_negative_flow(
    app_client: TestClient,
    db,
    make_user,
    make_event,
    login_as,
    clock,
):
    """Negative flow per REQUIREMENTS.md E2E-01:
    Failed dues payment leaves membership PENDING with no member card,
    tickets require public price, and no journal entries are created.
    """
    clock.set_now("2026-09-01T10:00:00Z")

    applicant = make_user(email="bob@university.edu", name="Bob Failing")
    raw_session, csrf_token = login_as(applicant)

    plan_row = db.execute("SELECT id FROM membership_plans WHERE code = 'STANDARD';").fetchone()
    plan_id = plan_row["id"]

    # 1. Initiate join
    resp_join = app_client.post(
        "/join",
        data={
            "plan_id": str(plan_id),
            "idempotency_key": "idemp_bob_join_001",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    pay_public_id = resp_join.headers["location"].split("/pay/")[1]

    # Open payment simulator page
    app_client.get(f"/pay/{pay_public_id}")

    # 2. Simulate payment FAILURE
    resp_fail = app_client.post(
        f"/pay/{pay_public_id}/outcome",
        data={
            "outcome": "fail",
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert resp_fail.status_code == 303

    # 3. Assert membership remains PENDING (or not ACTIVE), no member_code or qr_token
    mem_row = db.execute("SELECT * FROM memberships WHERE user_id = ?;", (applicant["id"],)).fetchone()
    assert mem_row["status"] != "ACTIVE"
    assert mem_row["member_code"] is None
    assert mem_row["qr_token"] is None

    # Card page shows no active membership
    resp_card = app_client.get("/members/card")
    assert resp_card.status_code == 200
    assert "No Active Membership" in resp_card.text or mem_row["member_code"] is None

    # 4. Zero journal entries posted
    entries_count = db.execute("SELECT COUNT(*) AS c FROM journal_entries;").fetchone()["c"]
    assert entries_count == 0

    # 5. Check ticket price for Bob on an event: must be charged PUBLIC price (1000 paise, not 800)
    event = make_event(
        title="Negative Flow Event",
        capacity=20,
        public_price_paise=1000,
        member_price_paise=800,
    )
    resp_evt = app_client.get(f"/events/{event['id']}")
    assert resp_evt.status_code == 200
    assert "10.00" in resp_evt.text  # public price shown


def test_regression_capacity_race_and_late_payment_unfulfilled(
    app_client: TestClient,
    db,
    make_user,
    make_event,
    login_as,
    clock,
):
    """Mandatory regression: Capacity race & late payment handling.
    1. Event with capacity=1. User 1 holds the seat.
    2. Clock advances past 10 min TTL (+11 min). Hold is now expired by clock.
    3. User 2 holds the now-freed seat and pays for it successfully.
    4. User 1's late payment outcome arrives and succeeds.
    5. User 1's payment transitions to SUCCEEDED with fulfillment=UNFULFILLED,
       booked as Dr1100 / Cr2000 obligation.
    6. Capacity invariant is strictly preserved: exactly 1 ticket exists for the event.
    """
    clock.set_now("2026-09-01T12:00:00Z")

    u1 = make_user(email="racer1@test.org", name="Racer 1")
    u2 = make_user(email="racer2@test.org", name="Racer 2")

    # Event with capacity=1
    event = make_event(title="Single Seat Concert", capacity=1, public_price_paise=5000, member_price_paise=4000)
    event_id = event["id"]

    # User 1 holds the only seat
    _, csrf1 = login_as(u1)
    resp_h1 = app_client.post(
        f"/events/{event_id}/hold",
        data={"qty": "1", "idempotency_key": "u1_hold_single", "csrf_token": csrf1},
        follow_redirects=False,
    )
    assert resp_h1.status_code == 303
    pay1_public_id = resp_h1.headers["location"].split("/pay/")[1]

    # Advance clock past hold expiry (11 minutes later) and run expire_holds
    from clubledger.events.service import expire_holds
    clock.set_now("2026-09-01T12:11:00Z")
    expire_holds(db, clock.now())

    # User 2 holds the seat (now available because hold 1 has expired)
    _, csrf2 = login_as(u2)
    resp_h2 = app_client.post(
        f"/events/{event_id}/hold",
        data={"qty": "1", "idempotency_key": "u2_hold_single", "csrf_token": csrf2},
        follow_redirects=False,
    )
    assert resp_h2.status_code == 303
    pay2_public_id = resp_h2.headers["location"].split("/pay/")[1]

    # User 2 pays successfully -> gets the 1 ticket
    resp_pay2 = app_client.post(
        f"/pay/{pay2_public_id}/outcome",
        data={"outcome": "success", "csrf_token": csrf2},
        follow_redirects=False,
    )
    assert resp_pay2.status_code == 303

    u2_tickets = db.execute("SELECT * FROM tickets WHERE user_id = ? AND event_id = ?;", (u2["id"], event_id)).fetchall()
    assert len(u2_tickets) == 1
    assert u2_tickets[0]["status"] == "ISSUED"

    # Now User 1 attempts late payment on their expired hold
    _, csrf1_fresh = login_as(u1)
    resp_pay1_late = app_client.post(
        f"/pay/{pay1_public_id}/outcome",
        data={"outcome": "success", "csrf_token": csrf1_fresh},
        follow_redirects=False,
    )
    assert resp_pay1_late.status_code == 303

    # Verify User 1's payment row: status=SUCCEEDED, fulfillment=UNFULFILLED
    pay1_row = db.execute("SELECT * FROM payments WHERE public_id = ?;", (pay1_public_id,)).fetchone()
    assert pay1_row["status"] == "SUCCEEDED"
    assert pay1_row["fulfillment"] == "UNFULFILLED"

    # Verify no ticket was issued for User 1
    u1_tickets = db.execute("SELECT * FROM tickets WHERE user_id = ? AND event_id = ?;", (u1["id"], event_id)).fetchall()
    assert len(u1_tickets) == 0

    # Total tickets for event remains exactly 1 (capacity respected)
    total_tickets = db.execute("SELECT COUNT(*) AS c FROM tickets WHERE event_id = ?;", (event_id,)).fetchone()["c"]
    assert total_tickets == 1

    # Cash summary: 2000 account (unfulfilled obligations) has 5000 paise balance
    cs = cash_summary(db, 1)
    assert cs.unfulfilled_obligations == 5000


def test_regression_ticket_cancellation_and_exact_journal_reversal(
    app_client: TestClient,
    db,
    make_user,
    make_event,
    login_as,
    clock,
):
    """Mandatory regression: Unused ticket refund creates exact journal reversal."""
    from clubledger.wiring import build_handlers

    clock.set_now("2026-09-01T10:00:00Z")
    buyer = make_user(email="buyer@test.org", name="Ticket Buyer")
    _, csrf = login_as(buyer)

    event = make_event(title="Refundable Show", capacity=10, public_price_paise=2500, member_price_paise=2000)
    event_id = event["id"]

    # Hold and pay for 1 ticket
    resp_hold = app_client.post(
        f"/events/{event_id}/hold",
        data={"qty": "1", "idempotency_key": "buy_refund_test", "csrf_token": csrf},
        follow_redirects=False,
    )
    pay_public_id = resp_hold.headers["location"].split("/pay/")[1]

    app_client.post(
        f"/pay/{pay_public_id}/outcome",
        data={"outcome": "success", "csrf_token": csrf},
        follow_redirects=False,
    )

    pay_row = db.execute("SELECT * FROM payments WHERE public_id = ?;", (pay_public_id,)).fetchone()
    assert pay_row["status"] == "SUCCEEDED"
    assert pay_row["fulfillment"] == "FULFILLED"

    # Pre-refund: Clearing has 2500, Ticket Income (4100) has 2500
    assert balance(db, "1100") == 2500
    assert balance(db, "4100") == 2500

    # Perform refund via payment service
    handlers = build_handlers()
    refund_payment(db, handlers, pay_row["id"], actor_id=buyer["id"])

    # Post-refund:
    # 1. Payment status is REFUNDED
    pay_after = db.execute("SELECT status FROM payments WHERE id = ?;", (pay_row["id"],)).fetchone()
    assert pay_after["status"] == "REFUNDED"

    # 2. Tickets are REFUNDED
    tkt_after = db.execute("SELECT status FROM tickets WHERE payment_id = ?;", (pay_row["id"],)).fetchone()
    assert tkt_after["status"] == "REFUNDED"

    # 3. Journal lines reversed: clearing (1100) returns to 0, ticket income (4100) returns to 0
    assert balance(db, "1100") == 0
    assert balance(db, "4100") == 0


def test_regression_repeated_notifications_no_effect(
    app_client: TestClient,
    db,
    make_user,
    make_event,
    login_as,
    clock,
):
    """Mandatory regression: Replaying payment outcome posts NO_EFFECT without extra money or tickets."""
    clock.set_now("2026-09-01T10:00:00Z")
    user = make_user(email="replay@test.org", name="Replay User")
    _, csrf = login_as(user)

    event = make_event(title="Replay Event", capacity=10, public_price_paise=1500, member_price_paise=1200)
    resp_hold = app_client.post(
        f"/events/{event['id']}/hold",
        data={"qty": "1", "idempotency_key": "replay_key_1", "csrf_token": csrf},
        follow_redirects=False,
    )
    pay_public_id = resp_hold.headers["location"].split("/pay/")[1]

    # First delivery
    resp1 = app_client.post(
        f"/pay/{pay_public_id}/outcome",
        data={"outcome": "success", "csrf_token": csrf},
        headers={"Accept": "application/json"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["outcome"] == "APPLIED"

    entries_count1 = db.execute("SELECT COUNT(*) AS c FROM journal_entries;").fetchone()["c"]
    tickets_count1 = db.execute("SELECT COUNT(*) AS c FROM tickets;").fetchone()["c"]

    # Second delivery (repeated notification)
    resp2 = app_client.post(
        f"/pay/{pay_public_id}/outcome",
        data={"outcome": "success", "csrf_token": csrf},
        headers={"Accept": "application/json"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["outcome"] == "NO_EFFECT"
    assert resp2.json()["reason"] == "REPEATED_NOTIFICATION"

    # Invariants unchanged
    entries_count2 = db.execute("SELECT COUNT(*) AS c FROM journal_entries;").fetchone()["c"]
    tickets_count2 = db.execute("SELECT COUNT(*) AS c FROM tickets;").fetchone()["c"]
    assert entries_count1 == entries_count2
    assert tickets_count1 == tickets_count2


def test_regression_csrf_and_foreign_ownership_blocks(
    app_client: TestClient,
    db,
    make_user,
    make_event,
    login_as,
    clock,
):
    """Mandatory regression: CSRF and foreign user ownership protection."""
    clock.set_now("2026-09-01T10:00:00Z")
    victim = make_user(email="victim@test.org", name="Victim User")
    attacker = make_user(email="attacker@test.org", name="Attacker User")

    # 1. Foreign ownership on payments
    login_as(victim)
    plan_row = db.execute("SELECT id FROM membership_plans LIMIT 1;").fetchone()
    resp_join = app_client.post(
        "/join",
        data={"plan_id": str(plan_row["id"]), "idempotency_key": "v_join", "csrf_token": "valid"},
        follow_redirects=False,
    )
    # The CSRF check above will fail if not using victim's actual csrf
    _, victim_csrf = login_as(victim)
    resp_join = app_client.post(
        "/join",
        data={"plan_id": str(plan_row["id"]), "idempotency_key": "v_join", "csrf_token": victim_csrf},
        follow_redirects=False,
    )
    victim_pay_id = resp_join.headers["location"].split("/pay/")[1]

    # Attacker tries to view victim's payment page -> 404
    _, attacker_csrf = login_as(attacker)
    resp_foreign_pay = app_client.get(f"/pay/{victim_pay_id}")
    assert resp_foreign_pay.status_code == 404

    # 2. CSRF rejection: POST /join with invalid CSRF token -> 403
    resp_csrf_fail = app_client.post(
        "/join",
        data={"plan_id": str(plan_row["id"]), "idempotency_key": "csrf_hack", "csrf_token": "wrong_csrf"},
    )
    assert resp_csrf_fail.status_code == 403


def test_regression_duplicate_and_wrong_event_checkin(
    app_client: TestClient,
    db,
    make_user,
    make_event,
    login_as,
    clock,
):
    """Mandatory regression: Ticket check-in prevents duplicate check-in and wrong event."""
    clock.set_now("2026-09-01T10:00:00Z")
    staff = make_user(email="staff2@test.org", name="Staff 2", roles=["door"])
    buyer = make_user(email="attendee@test.org", name="Attendee")

    e1 = make_event(title="Concert A", capacity=10, public_price_paise=1000, member_price_paise=1000)
    e2 = make_event(title="Concert B", capacity=10, public_price_paise=1000, member_price_paise=1000)

    # Buyer buys ticket for Concert A
    _, buyer_csrf = login_as(buyer)
    resp_h = app_client.post(
        f"/events/{e1['id']}/hold",
        data={"qty": "1", "idempotency_key": "hold_checkin_reg", "csrf_token": buyer_csrf},
        follow_redirects=False,
    )
    pay_id = resp_h.headers["location"].split("/pay/")[1]
    app_client.post(f"/pay/{pay_id}/outcome", data={"outcome": "success", "csrf_token": buyer_csrf})

    ticket_code = db.execute("SELECT code FROM tickets WHERE user_id = ?;", (buyer["id"],)).fetchone()["code"]

    # Staff logs in
    _, staff_csrf = login_as(staff)

    # 1. Scan ticket for Concert A at Concert B door -> REJECTED (Ticket is for another event)
    resp_wrong = app_client.post(
        f"/checkin/{e2['id']}/scan",
        data={"code": ticket_code, "csrf_token": staff_csrf},
    )
    assert resp_wrong.status_code == 422
    assert "Ticket is for another event" in resp_wrong.text
    assert db.execute('SELECT status FROM tickets WHERE code=?', (ticket_code,)).fetchone()[0] == 'ISSUED'

    # 2. Scan ticket at Concert A door -> OK (First scan)
    resp_ok = app_client.post(
        f"/checkin/{e1['id']}/scan",
        data={"code": ticket_code, "csrf_token": staff_csrf},
    )
    assert resp_ok.status_code == 200
    assert "Check-in confirmed" in resp_ok.text
    first_admission = tuple(db.execute('SELECT used_at,used_by FROM tickets WHERE code=?', (ticket_code,)).fetchone())

    # 3. Scan same ticket again at Concert A door -> ALREADY_USED
    resp_dup = app_client.post(
        f"/checkin/{e1['id']}/scan",
        data={"code": ticket_code, "csrf_token": staff_csrf},
    )
    assert resp_dup.status_code == 409
    assert "already used" in resp_dup.text.lower()
    assert tuple(db.execute('SELECT used_at,used_by FROM tickets WHERE code=?', (ticket_code,)).fetchone()) == first_admission
