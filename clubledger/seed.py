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
