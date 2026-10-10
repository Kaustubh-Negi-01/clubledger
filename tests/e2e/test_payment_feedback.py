import pytest


@pytest.mark.parametrize(
    "outcome,title",
    [("success", "You're all set!"), ("fail", "Payment didn't go through")],
)
def test_checkout_shows_actual_payment_result(
    app_client, db, make_user, login_as, clock, outcome, title
):
    clock.set_now("2026-09-01T10:00:00Z")
    user = make_user(email=f"feedback-{outcome}@college.edu")
    _, csrf = login_as(user)
    plan = db.execute(
        "SELECT id FROM membership_plans WHERE code='STANDARD'"
    ).fetchone()["id"]
    checkout = app_client.post(
        "/join",
        data={
            "plan_id": plan,
            "idempotency_key": f"feedback-{outcome}",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    url = checkout.headers["location"]
    pending = app_client.get(url + "?result=1")
    assert "data-payment-result" not in pending.text
    result = app_client.post(
        url + "/outcome",
        data={"outcome": outcome, "csrf_token": csrf},
        follow_redirects=False,
    )
    assert result.status_code == 303 and result.headers["location"] == url + "?result=1"
    page = app_client.get(result.headers["location"])
    assert page.status_code == 200 and title in page.text
    assert f'data-celebrate="{str(outcome == "success").lower()}"' in page.text
    assert 'aria-labelledby="payment-result-title"' in page.text
    assert "data-payment-result" not in app_client.get(url).text


def test_unfulfilled_success_is_not_a_purchase_celebration(
    app_client, db, make_user, login_as, clock
):
    from clubledger.payments.service import create_payment

    clock.set_now("2026-09-01T10:00:00Z")
    user = make_user(email="feedback-late@college.edu")
    _, csrf = login_as(user)
    payment = create_payment(
        db,
        user_id=user["id"],
        purpose="DUES",
        ref_table="memberships",
        ref_id=9999,
        amount_paise=200000,
    )
    db.commit()
    result = app_client.post(
        f"/pay/{payment.public_id}/outcome",
        data={"outcome": "success", "csrf_token": csrf},
        follow_redirects=False,
    )
    page = app_client.get(result.headers["location"])
    assert "Payment received — action needed" in page.text
    assert 'data-celebrate="false"' in page.text
    assert "You're all set!" not in page.text
