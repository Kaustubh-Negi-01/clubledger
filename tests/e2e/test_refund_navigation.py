"""Refunding one payment must leave the other refundable payments visible."""


def test_refund_returns_all_payments_without_hiding_other_refunds(
    app_client, db, make_user, make_event, login_as
):
    user = make_user(email="three-payments@college.edu")
    treasurer = make_user(email="refund-treasurer@college.edu", roles=["treasurer"])
    _, csrf = login_as(user)
    event = make_event()
    for index in range(3):
        response = app_client.post(
            f"/events/{event['id']}/hold",
            data=dict(qty=1, csrf_token=csrf, idempotency_key=f"refund-list-{index}"),
            follow_redirects=False,
        )
        assert response.status_code == 303
        response = app_client.post(
            response.headers["location"] + "/outcome",
            data=dict(outcome="success", csrf_token=csrf),
            follow_redirects=False,
        )
        assert response.status_code == 303
    ids = [
        row[0]
        for row in db.execute(
            "SELECT id FROM payments WHERE user_id=? ORDER BY id", (user["id"],)
        ).fetchall()
    ]
    _, csrf = login_as(treasurer)
    response = app_client.post(
        f"/admin/payments/{ids[0]}/refund",
        data=dict(csrf_token=csrf),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/payments?refunded={ids[0]}"
    page = app_client.get(response.headers["location"])
    assert f"Payment #{ids[0]} refunded successfully" in page.text
    from bs4 import BeautifulSoup

    actions = [
        form["action"]
        for form in BeautifulSoup(page.text, "html.parser").select(
            'form[action$="/refund"]'
        )
    ]
    assert f"/admin/payments/{ids[0]}/refund" not in actions
    assert all(f"/admin/payments/{pid}/refund" in actions for pid in ids[1:])
    assert [
        row[0]
        for row in db.execute(
            "SELECT status FROM payments WHERE user_id=? ORDER BY id", (user["id"],)
        ).fetchall()
    ] == ["REFUNDED", "SUCCEEDED", "SUCCEEDED"]
    assert "This filtered view" in app_client.get("/admin/payments?problem=1").text
