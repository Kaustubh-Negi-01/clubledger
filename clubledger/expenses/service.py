"""Expenses and Receipts domain service.

Owner: C
Assigned branch: codex/treasury-comms

Per CONTRACT.md §1.8, §3.5, §7, §12 and REQUIREMENTS.md EXP-01..07.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Mapping

from clubledger.core import clock
from clubledger.core.errors import DomainError
from clubledger.expenses.receipts import validate_and_save_receipt
from clubledger.journal import service as journal_service


def _get_open_term_id(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT id FROM terms WHERE status = 'OPEN'")
    row = cur.fetchone()
    if not row:
        raise DomainError("TERM_CLOSED", 409, "No active OPEN term")
    return int(row[0])


def submit_expense(
    conn: sqlite3.Connection,
    *,
    submitter_id: int,
    category_account_id: int,
    amount_paise: int,
    description: str,
    event_id: int | None = None,
    fundraiser_id: int | None = None,
    task_id: int | None = None,
) -> int:
    """Submit a new expense (EXP-01).

    - Category must have code in 5000-5099
    - amount_paise must be positive integer
    - term_id is OPEN term at submission
    - composite FK: task link requires that task's own fundraiser
    """
    if isinstance(amount_paise, bool) or not isinstance(amount_paise, int) or amount_paise <= 0:
        raise DomainError("VALIDATION", 422, "amount_paise must be positive integer")
    if not description or not description.strip():
        raise DomainError("VALIDATION", 422, "Description is required")

    # Validate category account code is in 5000-5099
    cur = conn.execute("SELECT code FROM accounts WHERE id = ?", (category_account_id,))
    row = cur.fetchone()
    if not row:
        raise DomainError("VALIDATION", 422, f"Account {category_account_id} not found")
    code = row[0]
    if not (code.startswith("50") and len(code) == 4):
        raise DomainError("VALIDATION", 422, f"Account {code} is not an expense category (5000-5099)")

    # Composite FK check for task & fundraiser link
    if task_id is not None:
        if fundraiser_id is None:
            raise DomainError("VALIDATION", 422, "task_id requires fundraiser_id")
        t_row = conn.execute(
            "SELECT fundraiser_id FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not t_row or t_row[0] != fundraiser_id:
            raise DomainError("VALIDATION", 422, f"Task {task_id} does not belong to fundraiser {fundraiser_id}")

    # Optional event existence check
    if event_id is not None:
        ev = conn.execute("SELECT 1 FROM events WHERE id = ?", (event_id,)).fetchone()
        if not ev:
            raise DomainError("VALIDATION", 422, f"Event {event_id} not found")

    term_id = _get_open_term_id(conn)
    now_ts = clock.now()

    try:
        cur = conn.execute(
            """
            INSERT INTO expenses (
                submitter_id, term_id, category_account_id, amount_paise, description,
                event_id, fundraiser_id, task_id, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'SUBMITTED', ?)
            """,
            (
                submitter_id,
                term_id,
                category_account_id,
                amount_paise,
                description.strip(),
                event_id,
                fundraiser_id,
                task_id,
                now_ts,
            ),
        )
        return int(cur.lastrowid)
    except sqlite3.IntegrityError as err:
        raise DomainError("VALIDATION", 422, str(err)) from err


def attach_receipt(
    conn: sqlite3.Connection,
    *,
    expense_id: int,
    uploader_id: int,
    file_content: bytes,
    original_filename: str,
    mime_type: str,
) -> int:
    """Attach a receipt to an existing expense (EXP-02, EXP-03)."""
    # Verify expense exists
    cur = conn.execute("SELECT submitter_id, status FROM expenses WHERE id = ?", (expense_id,))
    row = cur.fetchone()
    if not row:
        raise DomainError("NOT_FOUND", 404, f"Expense {expense_id} not found")

    submitter_id = row[0]
    if submitter_id != uploader_id:
        raise DomainError("NOT_FOUND", 404, "Expense not found")

    stored_name, safe_original, size_bytes, sha256_hex = validate_and_save_receipt(
        file_content, original_filename, mime_type
    )

    now_ts = clock.now()
    cur = conn.execute(
        """
        INSERT INTO receipts (
            uploader_id, expense_id, stored_name, original_name, mime, size_bytes, sha256, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uploader_id,
            expense_id,
            stored_name,
            safe_original,
            mime_type,
            size_bytes,
            sha256_hex,
            now_ts,
        ),
    )
    return int(cur.lastrowid)


def approve_expense(
    conn: sqlite3.Connection,
    *,
    expense_id: int,
    approver_user_id: int,
    decision_note: str | None = None,
) -> int:
    """Approve an expense (EXP-04).

    - Approver must not be submitter (SELF_APPROVAL)
    - Status must transition SUBMITTED -> APPROVED
    - Posts journal entry: Dr 50xx / Cr 2100 on the caller connection
    - Returns posted journal entry id
    """
    cur = conn.execute(
        "SELECT id, submitter_id, category_account_id, amount_paise, status FROM expenses WHERE id = ?",
        (expense_id,),
    )
    row = cur.fetchone()
    if not row:
        raise DomainError("NOT_FOUND", 404, f"Expense {expense_id} not found")

    e_id, submitter_id, cat_id, amount, status = row
    if submitter_id == approver_user_id:
        raise DomainError("SELF_APPROVAL", 403, "Approver cannot be the expense submitter")

    if status != "SUBMITTED":
        if status == "APPROVED":
            # Idempotent replay: return existing journal entry id
            j_cur = conn.execute(
                "SELECT id FROM journal_entries WHERE source_type = 'expense' AND source_id = ? AND source_event = 'approved'",
                (expense_id,),
            )
            j_row = j_cur.fetchone()
            if j_row:
                return int(j_row[0])
        raise DomainError("VALIDATION", 422, f"Cannot approve expense in status {status}")

    now_ts = clock.now()
    conn.execute(
        """
        UPDATE expenses
        SET status = 'APPROVED', decided_by = ?, decided_at = ?, decision_note = ?
        WHERE id = ? AND status = 'SUBMITTED'
        """,
        (approver_user_id, now_ts, decision_note, expense_id),
    )

    # Post journal entry (Dr 50xx / Cr 2100)
    expense_data = {
        "id": expense_id,
        "amount_paise": amount,
        "category_account_id": cat_id,
    }
    return journal_service.post_expense_approved(conn, expense_data)


def reject_expense(
    conn: sqlite3.Connection,
    *,
    expense_id: int,
    approver_user_id: int,
    decision_note: str | None = None,
) -> None:
    """Reject an expense (EXP-04). Approver cannot be submitter."""
    cur = conn.execute("SELECT submitter_id, status FROM expenses WHERE id = ?", (expense_id,))
    row = cur.fetchone()
    if not row:
        raise DomainError("NOT_FOUND", 404, f"Expense {expense_id} not found")

    submitter_id, status = row
    if submitter_id == approver_user_id:
        raise DomainError("SELF_APPROVAL", 403, "Approver cannot be the expense submitter")
    if status != "SUBMITTED":
        raise DomainError("VALIDATION", 422, f"Cannot reject expense in status {status}")

    now_ts = clock.now()
    conn.execute(
        """
        UPDATE expenses
        SET status = 'REJECTED', decided_by = ?, decided_at = ?, decision_note = ?
        WHERE id = ? AND status = 'SUBMITTED'
        """,
        (approver_user_id, now_ts, decision_note, expense_id),
    )


def pay_expense(
    conn: sqlite3.Connection,
    *,
    expense_id: int,
    payer_user_id: int,
) -> int:
    """Pay (reimburse) an approved expense (EXP-05, EXP-06).

    - Must be in APPROVED status (SUBMITTED -> 409)
    - Requires at least 1 receipt attached (no receipts -> 422)
    - Posts journal entry: Dr 2100 / Cr 1000 on caller connection
    - Idempotent: repeated pay returns existing journal entry id without duplicating effects
    """
    cur = conn.execute(
        "SELECT id, amount_paise, status FROM expenses WHERE id = ?",
        (expense_id,),
    )
    row = cur.fetchone()
    if not row:
        raise DomainError("NOT_FOUND", 404, f"Expense {expense_id} not found")

    e_id, amount, status = row

    if status == "SUBMITTED":
        raise DomainError("VALIDATION", 409, "Expense must be approved before payment")

    if status == "PAID":
        # Idempotent replay
        j_cur = conn.execute(
            "SELECT id FROM journal_entries WHERE source_type = 'expense' AND source_id = ? AND source_event = 'paid'",
            (expense_id,),
        )
        j_row = j_cur.fetchone()
        if j_row:
            return int(j_row[0])
        raise DomainError("VALIDATION", 422, "Expense already paid")

    if status != "APPROVED":
        raise DomainError("VALIDATION", 422, f"Cannot pay expense in status {status}")

    # Check for at least 1 receipt
    r_cur = conn.execute("SELECT COUNT(*) FROM receipts WHERE expense_id = ?", (expense_id,))
    receipt_count = int(r_cur.fetchone()[0])
    if receipt_count < 1:
        raise DomainError("VALIDATION", 422, "At least one receipt is required before paying an expense")

    now_ts = clock.now()
    conn.execute(
        """
        UPDATE expenses
        SET status = 'PAID', paid_by = ?, paid_at = ?
        WHERE id = ? AND status = 'APPROVED'
        """,
        (payer_user_id, now_ts, expense_id),
    )

    expense_data = {
        "id": expense_id,
        "amount_paise": amount,
    }
    return journal_service.post_expense_paid(conn, expense_data)


def void_expense(conn: sqlite3.Connection, expense_id: int, submitter_id: int) -> None:
    """Void a SUBMITTED expense by submitter."""
    cur = conn.execute("SELECT submitter_id, status FROM expenses WHERE id = ?", (expense_id,))
    row = cur.fetchone()
    if not row:
        raise DomainError("NOT_FOUND", 404, f"Expense {expense_id} not found")
    sub_id, status = row
    if sub_id != submitter_id:
        raise DomainError("FORBIDDEN", 403, "Only the submitter can void their expense")
    if status != "SUBMITTED":
        raise DomainError("VALIDATION", 422, f"Cannot void expense in status {status}")

    conn.execute("UPDATE expenses SET status = 'VOID' WHERE id = ?", (expense_id,))


def get_expense(conn: sqlite3.Connection, expense_id: int) -> dict[str, Any]:
    """Get full expense detail with category code and attached receipts."""
    cur = conn.execute(
        """
        SELECT e.id, e.submitter_id, e.term_id, e.category_account_id, a.code as category_code,
               e.amount_paise, e.description, e.event_id, e.fundraiser_id, e.task_id,
               e.status, e.decided_by, e.decided_at, e.decision_note,
               e.paid_by, e.paid_at, e.created_at, u.name as submitter_name
        FROM expenses e
        JOIN accounts a ON a.id = e.category_account_id
        JOIN users u ON u.id = e.submitter_id
        WHERE e.id = ?
        """,
        (expense_id,),
    )
    row = cur.fetchone()
    if not row:
        raise DomainError("NOT_FOUND", 404, f"Expense {expense_id} not found")

    r_cur = conn.execute(
        """
        SELECT id, uploader_id, stored_name, original_name, mime, size_bytes, created_at
        FROM receipts
        WHERE expense_id = ?
        ORDER BY id ASC
        """,
        (expense_id,),
    )
    receipts = [
        {
            "id": r[0],
            "uploader_id": r[1],
            "stored_name": r[2],
            "original_name": r[3],
            "mime": r[4],
            "size_bytes": r[5],
            "created_at": r[6],
        }
        for r in r_cur.fetchall()
    ]

    return {
        "id": row[0],
        "submitter_id": row[1],
        "term_id": row[2],
        "category_account_id": row[3],
        "category_code": row[4],
        "amount_paise": row[5],
        "description": row[6],
        "event_id": row[7],
        "fundraiser_id": row[8],
        "task_id": row[9],
        "status": row[10],
        "decided_by": row[11],
        "decided_at": row[12],
        "decision_note": row[13],
        "paid_by": row[14],
        "paid_at": row[15],
        "created_at": row[16],
        "submitter_name": row[17],
        "receipts": receipts,
    }
