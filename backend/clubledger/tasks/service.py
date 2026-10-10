# In plain English: Manages fundraisers, task ownership, progress and spending rollups.
"""Tasks and Fundraisers domain service.

Owner: C
Assigned branch: codex/treasury-comms

Per CONTRACT.md §1.7, §3, §12 and REQUIREMENTS.md TSK-01..04.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping

from clubledger.core import clock
from clubledger.core.errors import DomainError


VALID_TASK_STATUSES = {"TODO", "DOING", "DONE", "BLOCKED"}
VALID_FUNDRAISER_STATUSES = {"PLANNING", "ACTIVE", "DONE", "CANCELLED"}


def create_fundraiser(
    conn: sqlite3.Connection,
    *,
    term_id: int,
    title: str,
    goal_paise: int | None = None,
    status: str = "PLANNING",
) -> int:
    """Create a new fundraiser under a term."""
    if not title or not title.strip():
        raise DomainError("VALIDATION", 422, "Title is required")
    if goal_paise is not None and (
        isinstance(goal_paise, bool)
        or not isinstance(goal_paise, int)
        or goal_paise <= 0
    ):
        raise DomainError("VALIDATION", 422, "goal_paise must be positive integer")
    if status not in VALID_FUNDRAISER_STATUSES:
        raise DomainError("VALIDATION", 422, f"Invalid status: {status}")

    now_ts = clock.now()
    try:
        cur = conn.execute(
            """
            INSERT INTO fundraisers (term_id, title, goal_paise, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (term_id, title.strip(), goal_paise, status, now_ts),
        )
        return int(cur.lastrowid)
    except sqlite3.IntegrityError as err:
        raise DomainError("VALIDATION", 422, str(err)) from err


def get_fundraiser(conn: sqlite3.Connection, fundraiser_id: int) -> dict[str, Any]:
    """Retrieve fundraiser details and total spend vs goal."""
    cur = conn.execute(
        """
        SELECT f.id, f.term_id, f.title, f.goal_paise, f.status, f.created_at,
               COALESCE(SUM(CASE WHEN e.status IN ('APPROVED', 'PAID') THEN e.amount_paise ELSE 0 END), 0) AS total_spend_paise
        FROM fundraisers f
        LEFT JOIN expenses e ON e.fundraiser_id = f.id
        WHERE f.id = ?
        GROUP BY f.id
        """,
        (fundraiser_id,),
    )
    row = cur.fetchone()
    if not row:
        raise DomainError("NOT_FOUND", 404, f"Fundraiser {fundraiser_id} not found")
    return {
        "id": row[0],
        "term_id": row[1],
        "title": row[2],
        "goal_paise": row[3],
        "status": row[4],
        "created_at": row[5],
        "total_spend_paise": int(row[6]),
    }


def create_task(
    conn: sqlite3.Connection,
    *,
    fundraiser_id: int,
    title: str,
    owner_user_id: int | None = None,
    due_at: str | None = None,
    status: str = "TODO",
) -> int:
    """Create a task for a fundraiser."""
    if not title or not title.strip():
        raise DomainError("VALIDATION", 422, "Title is required")
    if status not in VALID_TASK_STATUSES:
        raise DomainError("VALIDATION", 422, f"Invalid status: {status}")

    if owner_user_id is not None:
        u = conn.execute(
            "SELECT 1 FROM users WHERE id = ?", (owner_user_id,)
        ).fetchone()
        if not u:
            raise DomainError("VALIDATION", 422, f"User {owner_user_id} does not exist")

    now_ts = clock.now()
    try:
        cur = conn.execute(
            """
            INSERT INTO tasks (fundraiser_id, title, owner_user_id, due_at, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (fundraiser_id, title.strip(), owner_user_id, due_at, status, now_ts),
        )
        return int(cur.lastrowid)
    except sqlite3.IntegrityError as err:
        raise DomainError("VALIDATION", 422, str(err)) from err


def update_task_status(
    conn: sqlite3.Connection,
    *,
    task_id: int,
    status: str,
    actor_user_id: int,
    is_staff: bool = False,
) -> None:
    """Update task status. Task owner or staff with tasks.manage can update status."""
    if status not in VALID_TASK_STATUSES:
        raise DomainError("VALIDATION", 422, f"Invalid status: {status}")

    cur = conn.execute("SELECT owner_user_id FROM tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    if not row:
        raise DomainError("NOT_FOUND", 404, f"Task {task_id} not found")

    owner_id = row[0]
    if not is_staff and owner_id != actor_user_id:
        raise DomainError(
            "FORBIDDEN",
            403,
            "Only the task owner or tasks.manage staff can update task status",
        )

    conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))


def get_fundraiser_board(
    conn: sqlite3.Connection, fundraiser_id: int
) -> dict[str, Any]:
    """Get on-track board showing tasks, counts per status, and overdue count (TSK-02)."""
    # Verify fundraiser exists
    get_fundraiser(conn, fundraiser_id)

    cur = conn.execute(
        """
        SELECT t.id, t.fundraiser_id, t.title, t.owner_user_id, t.due_at, t.status, t.created_at, u.name as owner_name
        FROM tasks t
        LEFT JOIN users u ON u.id = t.owner_user_id
        WHERE t.fundraiser_id = ?
        ORDER BY t.id ASC
        """,
        (fundraiser_id,),
    )
    tasks = []
    now_ts = clock.now()
    status_counts = {"TODO": 0, "DOING": 0, "DONE": 0, "BLOCKED": 0}
    overdue_count = 0

    for r in cur.fetchall():
        t_id, f_id, title, owner_id, due_at, status, created_at, owner_name = r
        status_counts[status] = status_counts.get(status, 0) + 1
        is_overdue = bool(due_at and due_at < now_ts and status != "DONE")
        if is_overdue:
            overdue_count += 1

        tasks.append(
            {
                "id": t_id,
                "fundraiser_id": f_id,
                "title": title,
                "owner_user_id": owner_id,
                "owner_name": owner_name,
                "due_at": due_at,
                "status": status,
                "created_at": created_at,
                "is_overdue": is_overdue,
            }
        )

    return {
        "fundraiser_id": fundraiser_id,
        "tasks": tasks,
        "counts": status_counts,
        "overdue_count": overdue_count,
    }
