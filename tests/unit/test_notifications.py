"""Real-data notices: ownership, truthful outcomes and persistent read state."""

import pytest

from clubledger.core import clock
from clubledger.core.errors import DomainError
from clubledger.notifications.service import mark_read, recent_notifications


def payment(db, user, status="FAILED", fulfillment="NONE"):
    return db.execute(
        "INSERT INTO payments(public_id,user_id,purpose,ref_table,ref_id,amount_paise,status,fulfillment,term_id,created_at) VALUES(?,?,'TICKET','ticket_holds',1,1000,?,?,1,?)",
        (
            f"notice-{user['id']}-{status}-{fulfillment}",
            user["id"],
            status,
            fulfillment,
            clock.now(),
        ),
    ).lastrowid


def announcement(db, user, title="Club meeting", status="PUBLISHED"):
    return db.execute(
        "INSERT INTO announcements(author_id,term_id,title,body,status,published_at,created_at) VALUES(?,1,?,'Read the update',?,?,?)",
        (
            user["id"],
            title,
            status,
            clock.now() if status == "PUBLISHED" else None,
            clock.now(),
        ),
    ).lastrowid


def test_only_own_payment_outcomes_are_visible_and_readable(db, make_user):
    owner = make_user(email="notice-owner@example.com")
    other = make_user(email="notice-other@example.com")
    payment(db, owner)
    notices = recent_notifications(db, owner["id"])
    assert notices[0]["title"] == "Ticket payment unsuccessful"
    assert "did not confirm" in notices[0]["message"]
    assert recent_notifications(db, other["id"]) == []
    with pytest.raises(DomainError) as error:
        mark_read(db, other["id"], notices[0]["key"])
    assert error.value.http_status == 404
    assert db.execute("SELECT COUNT(*) FROM notification_reads").fetchone()[0] == 0


def test_read_state_is_idempotent_per_user_and_new_outcome_is_unread(db, make_user):
    owner = make_user(email="notice-reader@example.com")
    other = make_user(email="notice-reader-two@example.com")
    ann_id = announcement(db, owner)
    mark_read(db, owner["id"], f"announcement:{ann_id}")
    mark_read(db, owner["id"], f"announcement:{ann_id}")
    assert not recent_notifications(db, owner["id"])[0]["unread"]
    assert recent_notifications(db, other["id"])[0]["unread"]
    assert db.execute("SELECT COUNT(*) FROM notification_reads").fetchone()[0] == 1
    pid = payment(db, owner, "SUCCEEDED", "FULFILLED")
    key = next(
        n["key"]
        for n in recent_notifications(db, owner["id"])
        if n["key"].startswith("payment:")
    )
    mark_read(db, owner["id"], key)
    db.execute(
        "UPDATE payments SET status='REFUNDED',refunded_at=? WHERE id=?",
        (clock.now(), pid),
    )
    refund = next(
        n
        for n in recent_notifications(db, owner["id"])
        if n["key"].startswith("payment:")
    )
    assert refund["unread"] and refund["title"] == "Ticket payment refunded"


def test_draft_announcements_are_hidden_and_unfulfilled_is_not_success(db, make_user):
    user = make_user(email="notice-states@example.com")
    announcement(db, user, status="DRAFT")
    payment(db, user, "SUCCEEDED", "UNFULFILLED")
    notices = recent_notifications(db, user["id"])
    assert len(notices) == 1
    assert notices[0]["title"] == "Ticket payment needs review"
    assert "could not be completed" in notices[0]["message"]


def test_membership_reminder_is_due_only_for_real_memberships(db, make_user, clock):
    user = make_user(email="notice-renew@example.com")
    clock.set_now("2027-07-10T12:00:00Z")
    db.execute(
        "INSERT INTO memberships(user_id,plan_id,membership_year,status,starts_at,expires_at,member_code,qr_token,created_at) VALUES(?,1,'2026-27','ACTIVE','2026-07-31T18:30:00Z','2027-07-31T18:30:00Z','NOTIFY-MEMBER','NOTIFY-QR',?)",
        (user["id"], clock.now()),
    )
    notices = recent_notifications(db, user["id"])
    assert len(notices) == 1 and "30 days" in notices[0]["message"]
    mark_read(db, user["id"])
    clock.set_now("2027-07-28T12:00:00Z")
    assert recent_notifications(db, user["id"])[0]["unread"]
    assert "7 days" in recent_notifications(db, user["id"])[0]["message"]
    db.execute("UPDATE memberships SET status='REVOKED' WHERE user_id=?", (user["id"],))
    assert recent_notifications(db, user["id"]) == []


def test_notification_routes_require_login_csrf_and_escape_content(
    app_client, db, make_user, login_as
):
    assert app_client.get("/notifications", follow_redirects=False).status_code == 303
    assert app_client.post("/notifications/read", data={}).status_code == 401
    user = make_user(email="notice-http@example.com")
    announcement(db, user, title="<script>alert('unsafe')</script>")
    login_as(user)
    page = app_client.get("/notifications")
    assert page.status_code == 200
    assert "&lt;script&gt;" in page.text
    assert "<script>alert('unsafe')</script>" not in page.text
    assert app_client.post("/notifications/read", data={}).status_code == 403
    import re

    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    assert (
        app_client.post(
            "/notifications/read", data={"csrf_token": token}, follow_redirects=False
        ).status_code
        == 303
    )
    assert all(not n["unread"] for n in recent_notifications(db, user["id"]))


def test_recent_feed_is_bounded_and_pending_payment_not_a_success(db, make_user):
    user = make_user(email="notice-bounds@example.com")
    for i in range(30):
        announcement(db, user, title=f"Update {i}")
    pid = payment(db, user)
    db.execute("UPDATE payments SET status='PENDING' WHERE id=?", (pid,))
    notices = recent_notifications(db, user["id"])
    assert len(notices) == 10
    assert all(n["key"].startswith("announcement:") for n in notices)
    assert notices[0]["title"] == "Club announcement: Update 29"


def test_received_payment_without_fulfillment_does_not_claim_issued_ticket(
    db, make_user
):
    user = make_user(email="notice-await-confirmation@example.com")
    payment(db, user, "SUCCEEDED", "NONE")
    notice = recent_notifications(db, user["id"])[0]
    assert notice["title"] == "Ticket payment received"
    assert "confirmation is still pending" in notice["message"]
