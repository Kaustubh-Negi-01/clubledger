"""Test entity factories.

Lazy factory helpers for user, event, and login fixtures.
Integrate application components dynamically as Owners A and B implement them.
If components are unavailable, functions raise or fixtures report blocked.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, Optional


def create_user(
    conn: sqlite3.Connection,
    *,
    email: str = "test@example.com",
    name: str = "Test User",
    password: str = "Secret123!",
    roles: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Create a user via clubledger auth/user services once implemented.
    
    Raises ImportError / NotImplementedError if user service does not exist yet.
    """
    try:
        # Check if auth/db models exist
        import clubledger.core.auth as auth_mod  # type: ignore
        if hasattr(auth_mod, "create_user"):
            return auth_mod.create_user(conn, email=email, name=name, password=password, roles=roles or [])
    except ImportError:
        pass

    raise NotImplementedError("User factory is waiting for Owner A's core.auth implementation.")


def create_event(
    conn: sqlite3.Connection,
    *,
    title: str = "Test Event",
    capacity: int = 100,
    public_price_paise: int = 50000,
    member_price_paise: int = 40000,
) -> Dict[str, Any]:
    """Create an event via clubledger events service once implemented.
    
    Raises ImportError / NotImplementedError if events service does not exist yet.
    """
    try:
        import clubledger.events.service as event_mod  # type: ignore
        if hasattr(event_mod, "create_event"):
            return event_mod.create_event(
                conn,
                title=title,
                capacity=capacity,
                public_price_paise=public_price_paise,
                member_price_paise=member_price_paise,
            )
    except ImportError:
        pass

    raise NotImplementedError("Event factory is waiting for Owner B's events.service implementation.")


def login_user(app_client: Any, user: Dict[str, Any]) -> Any:
    """Authenticate app_client as a given user.
    
    Raises NotImplementedError if auth route/service does not exist yet.
    """
    try:
        import clubledger.core.auth as auth_mod  # type: ignore
        if hasattr(auth_mod, "create_session"):
            # Set cookies on client
            pass
    except ImportError:
        pass

    raise NotImplementedError("Login factory is waiting for Owner A's core.auth session implementation.")
