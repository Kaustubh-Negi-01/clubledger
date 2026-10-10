"""The hosted demo keeps its login wall and explicit demo-account guidance."""

import pytest


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/dashboard",
        "/me",
        "/events",
        "/events/1",
        "/store",
        "/store/1",
        "/announcements",
        "/announcements/1",
        "/join",
        "/fundraisers",
        "/expenses",
        "/finance",
        "/admin/payments",
        "/docs",
        "/openapi.json",
    ],
)
def test_signed_out_club_pages_require_login(app_client, path):
    response = app_client.get(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"
    assert "no-store" in response.headers["cache-control"]
    response = app_client.get(path, headers={"Accept": "application/json"})
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


def test_hosted_demo_guidance_does_not_enable_dev_routes(
    app_client, monkeypatch, make_user, login_as
):
    monkeypatch.setenv("CLUBLEDGER_ENV", "prod")
    monkeypatch.setenv("CLUBLEDGER_DEMO_ACCOUNTS", "1")
    assert "student@skyline.edu" in app_client.get("/auth/login").text
    assert "DemoPassword123!" in app_client.get("/auth/login").text
    # Production cookies must stay secure while demo hints are visible.
    assert "Secure" in app_client.get("/auth/login").headers["set-cookie"]
    monkeypatch.setenv("CLUBLEDGER_ENV", "test")
    admin = make_user(email="demo-mode@college.edu", roles=["admin"])
    login_as(admin)
    monkeypatch.setenv("CLUBLEDGER_ENV", "prod")
    assert app_client.get("/dev/mail").status_code == 404


def test_demo_guidance_can_be_disabled(app_client, monkeypatch):
    monkeypatch.setenv("CLUBLEDGER_DEMO_ACCOUNTS", "0")
    assert "DemoPassword123!" not in app_client.get("/auth/login").text
