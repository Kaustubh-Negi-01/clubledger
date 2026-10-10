"""Verify resource moves still serve assets and keep code out of HTML attributes."""

from bs4 import BeautifulSoup


def test_moved_frontend_assets_are_served(app_client):
    for url in [
        "/static/app.css",
        "/static/page-layouts.css",
        "/static/app.js",
        "/static/campus-pass.svg",
        "/static/fonts/SpaceGrotesk-Variable.ttf",
    ]:
        response = app_client.get(url)
        assert response.status_code == 200 and response.content, url


def test_rendered_pages_have_no_inline_styles_or_event_handlers(
    app_client, make_user, login_as
):
    admin = make_user(email="layout-audit@college.edu", roles=["admin"])
    login_as(admin)
    paths = [
        "/dashboard",
        "/join",
        "/events",
        "/store",
        "/me/orders",
        "/fundraisers",
        "/expenses",
        "/announcements",
        "/finance",
        "/admin/events",
        "/verify",
        "/admin/checkin",
        "/admin/members",
        "/admin/store",
        "/admin/payments",
        "/admin/announcements",
        "/dev/mail",
        "/admin/adjustments",
        "/admin/close",
        "/admin/handover",
    ]
    for path in paths:
        response = app_client.get(path, headers={"Accept": "text/html"})
        assert response.status_code == 200, path
        document = BeautifulSoup(response.text, "html.parser")
        assert not document.select("[style], style"), path
        assert not [
            element
            for element in document.find_all()
            if any(name.lower().startswith("on") for name in element.attrs)
        ], path
        assert not [
            script
            for script in document.find_all("script")
            if script.get_text(strip=True)
        ], path
