"""Idempotent database seeding for roles and permissions per CONTRACT.md §4.3."""

import sqlite3
from typing import Final

from clubledger.core import clock


ALL_PERMISSIONS: Final[list[str]] = [
    "members.verify",
    "members.manage",
    "events.manage",
    "events.checkin",
    "store.manage",
    "store.fulfill",
    "comms.publish",
    "comms.mail_viewer",
    "tasks.manage",
    "expenses.approve",
    "expenses.pay",
    "receipts.view_all",
    "finance.view",
    "close.run",
    "handover.run",
    "payments.admin",
    "users.manage",
]

ROLE_PERMISSIONS_MAP: Final[dict[str, list[str]]] = {
    "admin": ALL_PERMISSIONS,
    "treasurer": [
        "finance.view",
        "expenses.approve",
        "expenses.pay",
        "receipts.view_all",
        "payments.admin",
        "close.run",
    ],
    "events": [
        "events.manage",
        "events.checkin",
        "members.verify",
    ],
    "door": [
        "events.checkin",
        "members.verify",
    ],
    "verifier": [
        "members.verify",
    ],
    "store": [
        "store.manage",
        "store.fulfill",
    ],
    "comms": [
        "comms.publish",
        "comms.mail_viewer",
        "tasks.manage",
    ],
}


def seed_roles_and_permissions(conn: sqlite3.Connection) -> None:
    """Seed fixed permissions, roles, and role_permissions idempotently."""
    now_iso = clock.now()

    # 1. Seed permissions
    for perm in ALL_PERMISSIONS:
        conn.execute(
            "INSERT INTO permissions (code, created_at) VALUES (?, ?) "
            "ON CONFLICT(code) DO NOTHING;",
            (perm, now_iso),
        )

    # Cache permission ids
    perm_rows = conn.execute("SELECT id, code FROM permissions;").fetchall()
    perm_id_map = {r["code"]: r["id"] for r in perm_rows}

    # 2. Seed roles
    for role_code in ROLE_PERMISSIONS_MAP.keys():
        conn.execute(
            "INSERT INTO roles (code, created_at) VALUES (?, ?) "
            "ON CONFLICT(code) DO NOTHING;",
            (role_code, now_iso),
        )

    # Cache role ids
    role_rows = conn.execute("SELECT id, code FROM roles;").fetchall()
    role_id_map = {r["code"]: r["id"] for r in role_rows}

    # 3. Seed role_permissions
    for role_code, perms in ROLE_PERMISSIONS_MAP.items():
        role_id = role_id_map[role_code]
        for perm_code in perms:
            perm_id = perm_id_map[perm_code]
            conn.execute(
                "INSERT INTO role_permissions (role_id, permission_id, created_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(role_id, permission_id) DO NOTHING;",
                (role_id, perm_id, now_iso),
            )


def seed_open_term(conn: sqlite3.Connection) -> int:
    """Ensure at least one valid OPEN term exists per CONTRACT §1.1."""
    row = conn.execute("SELECT id FROM terms WHERE status = 'OPEN' LIMIT 1;").fetchone()
    if row:
        return int(row["id"])

    # If no OPEN term exists, create a default OPEN term
    now_iso = clock.now()
    conn.execute(
        """
        INSERT INTO terms (label, starts_at, ends_at, status, created_at)
        VALUES ('2026-Fall', '2026-08-01T00:00:00Z', NULL, 'OPEN', ?)
        ON CONFLICT(label) DO UPDATE SET status = 'OPEN';
        """,
        (now_iso,),
    )
    term_row = conn.execute("SELECT id FROM terms WHERE status = 'OPEN' LIMIT 1;").fetchone()
    return int(term_row["id"])


def seed_demo_actors(conn: sqlite3.Connection) -> None:
    """Seed usable dev-only demo actors and roles idempotently without hardcoded production credentials."""
    from clubledger.core.auth import hash_password

    now_iso = clock.now()
    demo_password_hash = hash_password("DemoPassword123!")

    # Define demo actors: email, name, role
    actors = [
        ("admin@skyline.edu", "Demo Admin", "admin"),
        ("treasurer@skyline.edu", "Demo Treasurer", "treasurer"),
        ("events@skyline.edu", "Demo Events Staff", "events"),
        ("student@skyline.edu", "Demo Student", None),
    ]

    for email, name, role_code in actors:
        user = conn.execute("SELECT id FROM users WHERE email = ?;", (email,)).fetchone()
        if not user:
            cur = conn.execute(
                """
                INSERT INTO users (email, name, password_hash, is_active, created_at)
                VALUES (?, ?, ?, 1, ?);
                """,
                (email, name, demo_password_hash, now_iso),
            )
            user_id = cur.lastrowid
        else:
            user_id = user["id"]

        if role_code:
            role_row = conn.execute("SELECT id FROM roles WHERE code = ?;", (role_code,)).fetchone()
            if role_row:
                has_role = conn.execute(
                    "SELECT 1 FROM user_roles WHERE user_id = ? AND role_id = ? AND revoked_at IS NULL;",
                    (user_id, role_row["id"]),
                ).fetchone()
                if not has_role:
                    conn.execute(
                        """
                        INSERT INTO user_roles (user_id, role_id, granted_at, created_at)
                        VALUES (?, ?, ?, ?);
                        """,
                        (user_id, role_row["id"], now_iso, now_iso),
                    )


def seed_all(conn: sqlite3.Connection, demo: bool = False) -> None:
    """Central idempotent seed entrypoint per CONTRACT §14."""
    # 1. Roles and permissions
    seed_roles_and_permissions(conn)

    # 2. One valid OPEN financial term
    seed_open_term(conn)

    # 3. Membership plans (B)
    try:
        from clubledger.membership.service import seed_plans
        seed_plans(conn)
    except (ImportError, AttributeError):
        pass

    # 4. Events (B)
    try:
        from clubledger.events.service import seed_events
        seed_events(conn)
    except (ImportError, AttributeError):
        pass

    # 5. Demo actors
    if demo:
        seed_demo_actors(conn)
