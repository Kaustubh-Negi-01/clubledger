"""Test entity factories.

Provides helper functions for user, event, role assignment, and session login.
Used across integration and E2E tests.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, Optional

from clubledger.core.auth import COOKIE_SESSION, create_session, register_user
from clubledger.core import clock
from clubledger.core.db import connect


def create_user(
    conn: sqlite3.Connection,
    *,
    email: str = "test@example.com",
    name: str = "Test User",
    password: str = "Secret123!",
    roles: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Create a user with optional roles."""
    user_id = register_user(conn, email=email, name=name, password=password)

    if roles:
        for r_code in roles:
            role_row = conn.execute("SELECT id FROM roles WHERE code = ?;", (r_code,)).fetchone()
            if role_row:
                role_id = role_row["id"]
                conn.execute(
                    "INSERT INTO user_roles (user_id, role_id, granted_at, created_at) "
                    "VALUES (?, ?, ?, ?);",
                    (user_id, role_id, clock.now(), clock.now()),
                )

    conn.commit()
    return {
        "id": user_id,
        "email": email,
        "name": name,
        "password": password,
    }


def create_event(
    conn: sqlite3.Connection,
    *,
    title: str = "Test Event",
    venue: str = "Campus Hall",
    capacity: int = 100,
    public_price_paise: int = 1000,
    member_price_paise: int = 800,
    term_id: int | None = None,
) -> Dict[str, Any]:
    """Create an event in the events table."""
    if term_id is None:
        term_row = conn.execute("SELECT id FROM terms WHERE status = 'OPEN' LIMIT 1;").fetchone()
        term_id = term_row["id"] if term_row else 1

    now_str = clock.now()
    cur = conn.execute(
        "INSERT INTO events ("
        "  term_id, title, venue, starts_at, ends_at, capacity, "
        "  member_price_paise, public_price_paise, max_per_order, status, created_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, 4, 'ON_SALE', ?);",
        (
            term_id,
            title,
            venue,
            "2026-11-01T10:00:00Z",
            "2026-11-01T18:00:00Z",
            capacity,
            member_price_paise,
            public_price_paise,
            now_str,
        ),
    )
    conn.commit()
    return {
        "id": cur.lastrowid,
        "title": title,
        "capacity": capacity,
        "member_price_paise": member_price_paise,
        "public_price_paise": public_price_paise,
    }


def login_user(app_client: Any, user: Dict[str, Any], conn: sqlite3.Connection) -> tuple[str, str]:
    """Create a session for user and set session cookie on app_client.
    
    Returns (raw_session_token, csrf_token).
    """
    raw_token, csrf_token = create_session(conn, user["id"])
    app_client.cookies.set(COOKIE_SESSION, raw_token)
    return raw_token, csrf_token
