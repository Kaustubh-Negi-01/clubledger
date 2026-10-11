"""Browser workflow and period lifecycle acceptance tests on real migrated databases."""

import hashlib
import json
import sqlite3
import pytest
from clubledger.core.db import unit_of_work
from clubledger.comms import service as comms
from clubledger.close import service as close
from clubledger.reports.service import balance


def test_all_student_sections_are_reachable(app_client, make_user, login_as, clock):
    clock.set_now("2026-09-01T10:00:00Z")
    user = make_user(email="navigation@college.edu")
    login_as(user)
    for path in [
        "/me",
        "/dashboard",
        "/join",
        "/members/card",
        "/events",
        "/store",
        "/me/orders",
        "/fundraisers",
        "/expenses",
        "/announcements",
    ]:
        response = app_client.get(path, headers={"Accept": "text/html"})
        assert response.status_code == 200, (path, response.text)
        assert "Main navigation" in response.text
        assert "/static/app.css" in response.text
        assert "Financial ledger" not in response.text


def test_real_body_lengths_and_auth_csrf(app_client):
    for path in ["/auth/login", "/auth/register"]:
        response = app_client.get(path)
        assert len(response.content) == int(response.headers["content-length"])
        assert 'name="csrf_token"' in response.text
        assert app_client.cookies.get("cl_csrf")
    assert (
        app_client.post(
            "/auth/login",
            data={"email": "a@b.edu", "password": "12345678", "csrf_token": "foreign"},
        ).status_code
        == 403
    )


@pytest.mark.req("AUTH-07", "neg")
@pytest.mark.req("AUTH-08", "neg")
def test_all_mutating_routes_require_csrf(app_client, make_user, login_as):
    admin = make_user(email="csrf-sweep@college.edu", roles=["admin"])
    login_as(admin)
    for route in app_client.app.routes:
        methods = getattr(route, "methods", set())
        if not methods or route.path == "/webhooks/payments":
            continue
        import re

        path = re.sub(r"\{[^}]+\}", "999", route.path)
        for method in methods.intersection({"POST", "PATCH", "PUT", "DELETE"}):
            assert app_client.request(method, path, data={}).status_code == 403, (
                method,
                path,
            )


@pytest.mark.req("COM-01", "pos")
@pytest.mark.req("COM-02", "pos")
@pytest.mark.req("COM-04", "pos")
@pytest.mark.req("COM-05", "pos")
def test_publish_and_capture_are_exactly_once(db, make_user, clock):
    clock.set_now("2026-09-01T10:00:00Z")
    author = make_user(email="publisher@college.edu")
    comms.subscribe(db, "reader@college.edu")
    draft = comms.create_announcement(
        db, author["id"], "A real update", "Club meeting on Friday."
    )
    comms.publish(db, draft)
    comms.publish(db, draft)
    assert db.execute("SELECT COUNT(*) FROM mail_outbox").fetchone()[0] == 1
    assert comms.process_mail_outbox(db) == 1
    assert comms.process_mail_outbox(db) == 0
    assert db.execute("SELECT COUNT(*) FROM mail_capture").fetchone()[0] == 1
    row = db.execute("SELECT * FROM announcements WHERE id=?", (draft,)).fetchone()
    assert (
        row["status"] == "PUBLISHED"
        and row["published_at"]
        and row["author_id"] == author["id"]
    )


@pytest.mark.req("COM-01", "neg")
@pytest.mark.req("SEC-02", "pos")
def test_drafts_private_and_published_content_escaped(app_client, db, make_user, login_as):
    author = make_user(email="escape@college.edu")
    login_as(author)
    draft = comms.create_announcement(
        db, author["id"], "Hidden draft", "<script>alert(1)</script>"
    )
    assert app_client.get(f"/announcements/{draft}").status_code == 404
    comms.publish(db, draft)
    response = app_client.get(f"/announcements/{draft}")
    assert response.status_code == 200
    assert "&lt;script&gt;" in response.text
    assert "<script>alert(1)</script>" not in response.text


@pytest.mark.req("COM-02", "neg")
@pytest.mark.req("COM-03", "pos")
@pytest.mark.req("COM-04", "neg")
def test_unsubscribe_after_enqueue_suppresses_capture(db, make_user):
    author = make_user(email="unsubscribe-author@college.edu")
    subscriber = comms.subscribe(db, "unsubscriber@college.edu")
    assert comms.subscribe(db, "UNSUBSCRIBER@college.edu") == subscriber
    draft = comms.create_announcement(db, author["id"], "Queued", "Message")
    comms.publish(db, draft)
    token = db.execute(
        "SELECT unsub_token FROM subscribers WHERE id=?", (subscriber,)
    ).fetchone()[0]
    comms.unsubscribe(db, token)
    assert comms.process_mail_outbox(db) == 1
    row = db.execute("SELECT status,suppressed_reason FROM mail_outbox").fetchone()
    assert tuple(row) == ("SUPPRESSED", "UNSUBSCRIBED")
    assert db.execute("SELECT COUNT(*) FROM mail_capture").fetchone()[0] == 0
    comms.publish(db, draft)
    assert db.execute("SELECT COUNT(*) FROM mail_outbox").fetchone()[0] == 1


@pytest.mark.req("COM-03", "neg")
@pytest.mark.req("COM-05", "neg")
def test_invalid_subscription_and_immutable_publication(db, make_user):
    from clubledger.core.errors import DomainError

    with pytest.raises(DomainError):
        comms.subscribe(db, "invalid")
    with pytest.raises(DomainError):
        comms.unsubscribe(db, "unknown")
    author = make_user(email="immutable@college.edu")
    item = comms.create_announcement(db, author["id"], "Unchanging", "Original")
    comms.publish(db, item)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE announcements SET body=? WHERE id=?", ("Changed", item))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM announcements WHERE id=?", (item,))


@pytest.mark.req("AUTH-13", "pos")
def test_admin_screens_and_mail_permissions(app_client, make_user, login_as):
    admin = make_user(email="admin-screens@college.edu", roles=["admin"])
    login_as(admin)
    for path in [
        "/admin/events",
        "/admin/checkin",
        "/admin/members",
        "/admin/store",
        "/admin/payments",
        "/admin/announcements",
        "/dev/mail",
        "/admin/close",
        "/admin/handover",
        "/admin/adjustments",
        "/finance",
        "/finance/integrity",
    ]:
        response = app_client.get(path)
        assert response.status_code == 200, (path, response.text)
        assert "Main navigation" in response.text


def test_manage_events_search_and_status_filters(
    app_client, db, make_user, make_event, login_as
):
    admin = make_user(email="event-filter-admin@college.edu", roles=["admin"])
    photography = make_event(title="Photography Walk", venue="North Gate")
    design = make_event(title="Design Sprint", venue="Studio Two")
    db.execute("UPDATE events SET status='ON_SALE' WHERE id=?", (photography["id"],))
    db.execute("UPDATE events SET status='DRAFT' WHERE id=?", (design["id"],))
    login_as(admin)

    response = app_client.get("/admin/events?event_search=photo")
    assert response.status_code == 200
    assert "Photography Walk" in response.text
    assert "Design Sprint" not in response.text

    response = app_client.get("/admin/events?event_status=DRAFT")
    assert "Design Sprint" in response.text
    assert "Photography Walk" not in response.text

    response = app_client.get("/admin/events?event_search=missing")
    assert "No events match these filters." in response.text


@pytest.mark.req("AUTH-13", "neg")
def test_mail_view_denied_to_student_and_hidden_in_production(
    app_client, make_user, login_as, monkeypatch
):
    student = make_user(email="no-mail@college.edu")
    login_as(student)
    assert app_client.get("/dev/mail").status_code == 403
    monkeypatch.setenv("CLUBLEDGER_ENV", "prod")
    assert app_client.get("/dev/mail").status_code == 404


@pytest.mark.req("EXP-02", "neg")
@pytest.mark.req("EXP-03", "neg")
def test_receipt_upload_csrf_mime_and_ownership(app_client, db, make_user, login_as):
    from clubledger.expenses.service import submit_expense

    owner = make_user(email="receipt-owner@college.edu")
    other = make_user(email="receipt-other@college.edu")
    category = db.execute(
        "SELECT id FROM accounts WHERE type='EXPENSE' LIMIT 1"
    ).fetchone()[0]
    expense = submit_expense(
        db,
        submitter_id=owner["id"],
        category_account_id=category,
        amount_paise=10000,
        description="Receipt security",
    )
    _, csrf = login_as(owner)
    assert (
        app_client.post(
            f"/expenses/{expense}/receipt",
            files={"file": ("fake.png", b"<html>evil", "image/png")},
            data={"csrf_token": csrf},
        ).status_code
        == 422
    )
    assert (
        app_client.post(
            f"/expenses/{expense}/receipt",
            files={"file": ("receipt.pdf", b"%PDF-1.4\nreceipt", "application/pdf")},
        ).status_code
        == 403
    )
    _, foreign_csrf = login_as(other)
    assert (
        app_client.post(
            f"/expenses/{expense}/receipt",
            files={"file": ("receipt.pdf", b"%PDF-1.4\nreceipt", "application/pdf")},
            data={"csrf_token": foreign_csrf},
        ).status_code
        == 404
    )
    assert db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 0


@pytest.mark.req("E2E-02", "pos")
@pytest.mark.req("CLS-01", "pos")
@pytest.mark.req("CLS-02", "pos")
@pytest.mark.req("CLS-03", "pos")
@pytest.mark.req("CLS-05", "pos")
@pytest.mark.req("CLS-07", "pos")
@pytest.mark.req("CLS-08", "pos")
@pytest.mark.req("EXP-02", "pos")
@pytest.mark.req("EXP-03", "pos")
def test_full_semester_merch_expense_settlement_close_handover(
    app_client, db, make_user, make_event, login_as, clock
):
    clock.set_now("2026-09-01T10:00:00Z")
    student = make_user(email="semester-student@college.edu")
    admin = make_user(email="semester-admin@college.edu", roles=["admin"])
    outgoing = make_user(email="outgoing@college.edu", roles=["events"])
    incoming = make_user(email="incoming@college.edu")
    event = make_event()
    _, csrf = login_as(student)
    plan = db.execute(
        "SELECT id FROM membership_plans WHERE code='STANDARD'"
    ).fetchone()[0]
    response = app_client.post(
        "/join",
        data=dict(plan_id=plan, idempotency_key="semester-dues", csrf_token=csrf),
        follow_redirects=False,
    )
    assert response.status_code == 303
    payment_url = response.headers["location"]
    assert (
        app_client.post(
            payment_url + "/outcome",
            data=dict(outcome="success", csrf_token=csrf),
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert (
        app_client.get("/me", headers={"Accept": "application/json"}).json()[
            "membership"
        ]["status"]
        == "ACTIVE"
    )
    product = db.execute(
        "INSERT INTO products(name,base_price_paise,created_at) VALUES(?,?,?)",
        ("Semester tee", 50000, clock.now()),
    ).lastrowid
    variant = db.execute(
        "INSERT INTO variants(product_id,sku,size,physical_qty,created_at) VALUES(?,?,?,?,?)",
        (product, "SEM-M", "M", 2, clock.now()),
    ).lastrowid
    response = app_client.post(
        "/store/reserve",
        data=dict(
            variant_id=variant, qty=1, idempotency_key="semester-merch", csrf_token=csrf
        ),
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    assert (
        app_client.post(
            response.headers["location"] + "/outcome",
            data=dict(outcome="success", csrf_token=csrf),
            follow_redirects=False,
        ).status_code
        == 303
    )
    order = db.execute(
        "SELECT id,status FROM merch_orders WHERE user_id=?", (student["id"],)
    ).fetchone()
    assert order["status"] == "PAID"
    category = db.execute(
        "SELECT id FROM accounts WHERE type='EXPENSE' LIMIT 1"
    ).fetchone()[0]
    response = app_client.post(
        "/expenses/submit",
        data=dict(
            category_account_id=category,
            amount="125.50",
            description="Poster printing",
            csrf_token=csrf,
        ),
        follow_redirects=False,
    )
    assert response.status_code == 303
    expense = db.execute(
        "SELECT id FROM expenses WHERE submitter_id=?", (student["id"],)
    ).fetchone()[0]
    upload = app_client.post(
        f"/expenses/{expense}/receipt",
        data={"csrf_token": csrf},
        files={"file": ("invoice.pdf", b"%PDF-1.4\nDemo invoice", "application/pdf")},
        follow_redirects=False,
    )
    assert upload.status_code == 303, upload.text
    receipt = db.execute(
        "SELECT id FROM receipts WHERE expense_id=?", (expense,)
    ).fetchone()[0]
    assert app_client.get(f"/receipts/{receipt}").status_code == 200
    _, admin_csrf = login_as(admin)
    assert (
        app_client.post(
            f"/admin/store/orders/{order['id']}/pickup",
            data={"csrf_token": admin_csrf},
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert (
        app_client.post(
            f"/admin/expenses/{expense}/approve",
            data={"csrf_token": admin_csrf},
            follow_redirects=False,
        ).status_code
        == 303
    )
    clock.set_now("2026-09-02T10:01:00Z")
    _, admin_csrf = login_as(admin)
    assert (
        app_client.post(
            "/admin/settle", data={"csrf_token": admin_csrf}, follow_redirects=False
        ).status_code
        == 303
    )
    assert (
        app_client.post(
            f"/admin/expenses/{expense}/pay",
            data={"csrf_token": admin_csrf},
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert app_client.get(
        "/finance/integrity", headers={"Accept": "application/json"}
    ).json()["passed"]
    cash_before = balance(db, "1000")
    memberships_before = [tuple(row) for row in db.execute("SELECT * FROM memberships")]
    response = app_client.post(
        "/admin/close",
        data=dict(csrf_token=admin_csrf, term_id=1, confirmation="CLOSE"),
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    snapshot = db.execute("SELECT * FROM close_snapshots WHERE term_id=1").fetchone()
    assert snapshot
    assert (
        hashlib.sha256(snapshot["totals_json"].encode()).hexdigest()
        == snapshot["content_sha256"]
    )
    totals = json.loads(snapshot["totals_json"])
    assert all(a["opening"] + a["movement"] == a["closing"] for a in totals["accounts"])
    assert balance(db, "1000") == cash_before
    assert memberships_before == [
        tuple(row) for row in db.execute("SELECT * FROM memberships")
    ]
    old = db.execute("SELECT * FROM terms WHERE id=1").fetchone()
    new = db.execute("SELECT * FROM terms WHERE status='OPEN'").fetchone()
    assert new["starts_at"] == old["ends_at"]
    assert app_client.get(f"/snapshots/{snapshot['id']}").status_code == 200
    _, outgoing_csrf = login_as(outgoing)
    outgoing_cookie = app_client.cookies.get("cl_session")
    _, admin_csrf = login_as(admin)
    response = app_client.post(
        "/admin/handover",
        data=dict(
            csrf_token=admin_csrf,
            term_id=1,
            from_user_id=outgoing["id"],
            to_user_id=incoming["id"],
            role_codes="events",
            notes="Semester complete",
        ),
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    assert db.execute("SELECT COUNT(*) FROM officer_handover").fetchone()[0] == 1
    from clubledger.security.auth import load_session

    assert outgoing_cookie and load_session(db, outgoing_cookie) is None
    _, incoming_csrf = login_as(incoming)
    assert app_client.get("/admin/events").status_code == 200
    _, student_csrf = login_as(student)
    response = app_client.post(
        f"/events/{event['id']}/hold",
        data=dict(qty=1, idempotency_key="new-term-ticket", csrf_token=student_csrf),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert (
        app_client.post(
            response.headers["location"] + "/outcome",
            data=dict(outcome="success", csrf_token=student_csrf),
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert (
        db.execute("SELECT term_id FROM payments ORDER BY id DESC LIMIT 1").fetchone()[
            0
        ]
        == new["id"]
    )
    assert (
        db.execute(
            "SELECT totals_json FROM close_snapshots WHERE id=?", (snapshot["id"],)
        ).fetchone()[0]
        == snapshot["totals_json"]
    )


@pytest.mark.req("E2E-02", "neg")
@pytest.mark.req("CLS-01", "neg")
@pytest.mark.req("CLS-03", "neg")
def test_close_blocked_is_atomic(app_client, db, make_user, login_as, clock):
    clock.set_now("2026-09-01T10:00:00Z")
    admin = make_user(email="blocked-close@college.edu", roles=["admin"])
    _, csrf = login_as(admin)
    from clubledger.journal.service import post_entry
    from clubledger.core.types import Line

    post_entry(
        db,
        term_id=1,
        entry_date=clock.now(),
        source_type="adjustment",
        source_id=1,
        source_event="opening-test",
        memo="Test obligation",
        lines=[Line("1100", 10000, 0), Line("2000", 0, 10000)],
    )
    response = app_client.post(
        "/admin/close",
        data=dict(csrf_token=csrf, term_id=1, confirmation="CLOSE"),
        follow_redirects=False,
    )
    assert response.status_code == 409 and response.json()["code"] == "CLOSE_BLOCKED"
    assert db.execute("SELECT COUNT(*) FROM close_snapshots").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM close_checks").fetchone()[0] == 0
    assert (
        db.execute("SELECT COUNT(*) FROM terms WHERE status='OPEN'").fetchone()[0] == 1
    )


@pytest.mark.req("CLS-02", "neg")
@pytest.mark.req("CLS-07", "neg")
def test_snapshot_immutable_and_handover_before_close_blocked(db, make_user, clock):
    from clubledger.core.errors import DomainError

    clock.set_now("2026-09-01T10:00:00Z")
    admin = make_user(email="snapshot-admin@college.edu", roles=["admin"])
    incoming = make_user(email="snapshot-incoming@college.edu")
    with pytest.raises(DomainError):
        with unit_of_work() as conn:
            close.run_handover(conn, 1, admin["id"], incoming["id"], ["admin"])
    with unit_of_work() as conn:
        identifier = close.run_close(conn, 1, admin["id"])
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE close_snapshots SET totals_json=? WHERE id=?", ("{}", identifier)
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM close_snapshots WHERE id=?", (identifier,))
