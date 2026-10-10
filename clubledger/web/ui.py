"""Shared page context; navigation and account information come from live data."""
from pathlib import Path
from fastapi.templating import Jinja2Templates
from clubledger.core.auth import COOKIE_SESSION, load_session, get_user_permissions
from clubledger.core.db import connect
from clubledger.config import get_db_path, get_env
from clubledger.core import clock

templates = Jinja2Templates(directory=str(Path(__file__).parent / 'templates'))


def viewer(request):
    conn = connect(get_db_path())
    try:
        token = request.cookies.get(COOKIE_SESSION)
        session = load_session(conn, token) if token else None
        user = dict(conn.execute('SELECT id,name,email FROM users WHERE id=?', (session.user_id,)).fetchone()) if session else None
        return dict(user=user, csrf=session.csrf_token if session else '', permissions=get_user_permissions(conn, session.user_id) if session else set(), env=get_env(), now=clock.now())
    finally:
        conn.close()


def render(request, name, **context):
    return templates.TemplateResponse(request=request, name=name, context=context)
