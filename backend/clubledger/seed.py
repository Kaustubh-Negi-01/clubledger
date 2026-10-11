# In plain English: Creates initial roles and permissions and, when requested, realistic demo records.
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
        # Built-in roles have an exact permission set, never accumulated admin privileges.
        permitted_ids = [perm_id_map[code] for code in perms]
        placeholders = ",".join("?" for _ in permitted_ids)
        conn.execute(
            f"DELETE FROM role_permissions WHERE role_id=? AND permission_id NOT IN ({placeholders})",
            (role_id, *permitted_ids),
        )
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

    previous = conn.execute(
        "SELECT * FROM terms WHERE status='CLOSED' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if previous:
        return conn.execute(
            "INSERT INTO terms(label,starts_at,status,created_at) VALUES(?,?,'OPEN',?)",
            (f"Period after {previous['id']}", previous["ends_at"], clock.now()),
        ).lastrowid

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
    term_row = conn.execute(
        "SELECT id FROM terms WHERE status = 'OPEN' LIMIT 1;"
    ).fetchone()
    return int(term_row["id"])


def repair_demo_roles(conn: sqlite3.Connection) -> None:
    """Repair only named demo accounts; preserve ordinary users and role history."""
    assignments = {
        "admin@skyline.edu": "admin", "treasurer@skyline.edu": "treasurer",
        "events@skyline.edu": "events", "store@skyline.edu": "store",
        "comms@skyline.edu": "comms", "student@skyline.edu": None,
        "incoming@skyline.edu": None,
    }
    now = clock.now()
    for email, role in assignments.items():
        user = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if not user:
            continue
        desired = conn.execute("SELECT id FROM roles WHERE code=?", (role,)).fetchone() if role else None
        conn.execute(
            "UPDATE user_roles SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL AND role_id<>?",
            (now, user["id"], desired["id"] if desired else -1),
        )
        if desired and not conn.execute(
            "SELECT 1 FROM user_roles WHERE user_id=? AND role_id=? AND revoked_at IS NULL",
            (user["id"], desired["id"]),
        ).fetchone():
            conn.execute("INSERT INTO user_roles(user_id,role_id,granted_at,created_at) VALUES(?,?,?,?)",
                         (user["id"], desired["id"], now, now))


def seed_demo_actors(conn: sqlite3.Connection) -> None:
    """Seed usable dev-only demo actors and roles idempotently without hardcoded production credentials."""
    from clubledger.security.auth import hash_password

    now_iso = clock.now()
    demo_password_hash = hash_password("DemoPassword123!")

    # Define demo actors: email, name, role
    actors = [
        ("admin@skyline.edu", "Demo Admin", "admin"),
        ("treasurer@skyline.edu", "Demo Treasurer", "treasurer"),
        ("events@skyline.edu", "Demo Events Staff", "events"),
        ("student@skyline.edu", "Demo Student", None),
        ("store@skyline.edu", "Store Officer", "store"),
        ("comms@skyline.edu", "Communications Officer", "comms"),
        ("incoming@skyline.edu", "Incoming Officer", None),
    ]

    for email, name, role_code in actors:
        user = conn.execute(
            "SELECT id FROM users WHERE email = ?;", (email,)
        ).fetchone()
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
            role_row = conn.execute(
                "SELECT id FROM roles WHERE code = ?;", (role_code,)
            ).fetchone()
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


    repair_demo_roles(conn)


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
        seed_demo_content(conn)


def seed_demo_content(conn):
    from clubledger.tasks.service import create_fundraiser, create_task
    from clubledger.comms.service import create_announcement, publish, subscribe
    from datetime import datetime, timedelta, timezone

    now = clock.now()
    student = conn.execute(
        "SELECT id FROM users WHERE email='student@skyline.edu'"
    ).fetchone()["id"]
    admin = conn.execute(
        "SELECT id FROM users WHERE email='admin@skyline.edu'"
    ).fetchone()["id"]
    term = seed_open_term(conn)
    if not conn.execute("SELECT 1 FROM products").fetchone():
        for name, description, price, sizes in [
            (
                "Club essentials tee",
                "Heavyweight cotton. A simple mark of belonging.",
                65000,
                ["S", "M", "L", "XL"],
            ),
            (
                "Campus carry tote",
                "A reusable canvas tote for everyday campus life.",
                35000,
                ["One size"],
            ),
        ]:
            product = conn.execute(
                "INSERT INTO products(name,description,base_price_paise,created_at) VALUES(?,?,?,?)",
                (name, description, price, now),
            ).lastrowid
            for size in sizes:
                conn.execute(
                    "INSERT INTO variants(product_id,sku,size,physical_qty,created_at) VALUES(?,?,?,?,?)",
                    (product, f"CL-{product}-{size}", size, 20, now),
                )
    if not conn.execute("SELECT 1 FROM fundraisers").fetchone():
        fundraiser = create_fundraiser(
            conn,
            term_id=term,
            title="Campus library drive",
            goal_paise=10000000,
            status="ACTIVE",
        )
        due = (
            (datetime.fromisoformat(now.replace("Z", "+00:00")) + timedelta(days=7))
            .isoformat()
            .replace("+00:00", "Z")
        )
        create_task(
            conn,
            fundraiser_id=fundraiser,
            title="Design the volunteer sign-up poster",
            owner_user_id=student,
            due_at=due,
        )
        create_task(
            conn,
            fundraiser_id=fundraiser,
            title="Confirm collection desks and volunteers",
            owner_user_id=admin,
            due_at=due,
            status="DOING",
        )
    if not conn.execute("SELECT 1 FROM announcements").fetchone():
        subscribe(conn, "student@skyline.edu", student)
        announcement = create_announcement(
            conn,
            admin,
            "Welcome to the new club workspace",
            "Discover upcoming events, join the association, and follow the campus library drive. ClubLedger brings our work and financial records together. This is seeded demonstration content.",
        )
        publish(conn, announcement)
