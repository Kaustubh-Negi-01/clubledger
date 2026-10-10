# In plain English: Loads the current user and permissions and renders shared Jinja page context.
"""Shared page context; navigation and account information come from live data."""

from pathlib import Path
import os
from fastapi.templating import Jinja2Templates
from clubledger.core.auth import COOKIE_SESSION, load_session, get_user_permissions
from clubledger.core.db import connect
from clubledger.config import get_db_path, get_env
from clubledger.core import clock

from clubledger.paths import TEMPLATES_DIR
from clubledger.presentation.navigation import MAIN_NAVIGATION, OPERATIONS_NAVIGATION

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def viewer(request):
    """Read the current account and permissions for the shared page layout."""
    conn = connect(get_db_path())
    try:
        token = request.cookies.get(COOKIE_SESSION)
        session = load_session(conn, token) if token else None
        user = (
            dict(
                conn.execute(
                    "SELECT id,name,email FROM users WHERE id=?", (session.user_id,)
                ).fetchone()
            )
            if session
            else None
        )
        return dict(
            user=user,
            csrf=session.csrf_token if session else "",
            permissions=get_user_permissions(conn, session.user_id)
            if session
            else set(),
            env=get_env(),
            show_demo_accounts=os.environ.get(
                "CLUBLEDGER_DEMO_ACCOUNTS", "1" if get_env() != "prod" else "0"
            )
            == "1",
            cloud_database=getattr(conn, "dialect", None) == "postgres",
            now=clock.now(),
            main_navigation=MAIN_NAVIGATION,
            operations_navigation=OPERATIONS_NAVIGATION,
        )
    finally:
        conn.close()


def render(request, name, **context):
    """Fill an HTML template with the supplied data and return the rendered page."""
    return templates.TemplateResponse(request=request, name=name, context=context)
