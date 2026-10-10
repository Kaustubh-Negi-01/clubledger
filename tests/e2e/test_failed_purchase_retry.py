"""Failed payments release purchases; retry never activates the failed attempt."""

from clubledger.core import clock


def join(client, csrf, key):
    response = client.post(
        "/join",
        data=dict(plan_id=1, csrf_token=csrf, idempotency_key=key),
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return response.headers["location"]


def outcome(client, url, csrf, value):
    response = client.post(
        url + "/outcome",
        data=dict(outcome=value, csrf_token=csrf),
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text


def test_failed_membership_can_retry_without_false_membership(
    app_client, db, make_user, login_as
):
    user = make_user(email="retry-dues@college.edu")
    _, csrf = login_as(user)
    old = join(app_client, csrf, "dues-first")
    assert join(app_client, csrf, "dues-resume") == old
    assert db.execute("SELECT COUNT(*) FROM memberships").fetchone()[0] == 1
    outcome(app_client, old, csrf, "fail")
    assert db.execute("SELECT status FROM memberships").fetchone()[0] == "CANCELLED"
    page = app_client.get("/join").text
    assert "PAYMENT FAILED" in page and "Renewal opens 30 days" not in page
    assert (
        "do not currently have an active membership"
        in app_client.get("/members/card").text
    )
    new = join(app_client, csrf, "dues-retry")
    assert new != old
    # A late success for the failed checkout is money for review, not activation.
    outcome(app_client, old, csrf, "success")
    assert (
        db.execute("SELECT COUNT(*) FROM memberships WHERE status='ACTIVE'").fetchone()[
            0
        ]
        == 0
    )
    outcome(app_client, new, csrf, "success")
    assert (
        db.execute("SELECT COUNT(*) FROM memberships WHERE status='ACTIVE'").fetchone()[
            0
        ]
        == 1
    )
    assert "Renewal opens 30 days" in app_client.get("/join").text


def test_failed_merch_releases_stock_once_and_retry_succeeds(
    app_client, db, make_user, login_as
):
    user = make_user(email="retry-store@college.edu")
    _, csrf = login_as(user)
    product = db.execute(
        "INSERT INTO products(name,base_price_paise,created_at) VALUES(?,?,?)",
        ("Last tote", 35000, clock.now()),
    ).lastrowid
    variant = db.execute(
        "INSERT INTO variants(product_id,sku,size,physical_qty,created_at) VALUES(?,?,?,?,?)",
        (product, "LAST-TOTE", "One size", 1, clock.now()),
    ).lastrowid

    def reserve(key):
        response = app_client.post(
            "/store/reserve",
            data=dict(variant_id=variant, qty=1, idempotency_key=key, csrf_token=csrf),
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text
        return response.headers["location"]

    old = reserve("tote-first")
    outcome(app_client, old, csrf, "fail")
    outcome(app_client, old, csrf, "fail")
    row = db.execute(
        "SELECT physical_qty,reserved_qty FROM variants WHERE id=?", (variant,)
    ).fetchone()
    assert tuple(row) == (1, 0)
    assert db.execute("SELECT status FROM merch_orders").fetchone()[0] == "CANCELLED"
    assert db.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0] == 0
    page = app_client.get("/me/orders").text
    assert "PAYMENT FAILED" in page and "reservation has been released" in page
    new = reserve("tote-retry")
    outcome(app_client, old, csrf, "success")
    assert (
        db.execute("SELECT COUNT(*) FROM merch_orders WHERE status='PAID'").fetchone()[
            0
        ]
        == 0
    )
    outcome(app_client, new, csrf, "success")
    assert (
        db.execute("SELECT COUNT(*) FROM merch_orders WHERE status='PAID'").fetchone()[
            0
        ]
        == 1
    )
    assert tuple(
        db.execute(
            "SELECT physical_qty,reserved_qty FROM variants WHERE id=?", (variant,)
        ).fetchone()
    ) == (1, 1)


def test_failed_ticket_releases_last_seat(
    app_client, db, make_user, make_event, login_as
):
    user = make_user(email="retry-ticket@college.edu")
    _, csrf = login_as(user)
    event = make_event(capacity=1)

    def reserve(key):
        response = app_client.post(
            f"/events/{event['id']}/hold",
            data=dict(qty=1, idempotency_key=key, csrf_token=csrf),
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text
        return response.headers["location"]

    old = reserve("seat-first")
    outcome(app_client, old, csrf, "fail")
    assert db.execute("SELECT status FROM ticket_holds").fetchone()[0] == "RELEASED"
    assert db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 0
    new = reserve("seat-retry")
    outcome(app_client, new, csrf, "success")
    assert db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 1
