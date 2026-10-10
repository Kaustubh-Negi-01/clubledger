"""Journal domain service.

Owner: C
Assigned branch: codex/treasury-comms

Provides double-entry journal operations adhering to CONTRACT.md §1.6, §6, §7.
All functions take a connection owned by the caller and never call BEGIN, COMMIT, or ROLLBACK.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Mapping, Sequence

from clubledger.core.types import Line
from clubledger.core.errors import DomainError
from clubledger.core import clock


def _get_account_id(conn: sqlite3.Connection, code: str) -> int:
    cur = conn.execute("SELECT id FROM accounts WHERE code = ?", (code,))
    row = cur.fetchone()
    if not row:
        raise DomainError("VALIDATION", 422)
    return int(row[0])


def _get_open_term_id(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT id FROM terms WHERE status = 'OPEN'")
    row = cur.fetchone()
    if not row:
        raise DomainError("TERM_CLOSED", 409)
    return int(row[0])


def _validate_paise(val: Any) -> int:
    """Validate paise is a strict non-negative integer, rejecting bool/float/strings."""
    if isinstance(val, bool) or not isinstance(val, int) or val < 0:
        raise DomainError("VALIDATION", 422)
    return val


def _extract_field(obj: Any, key: str) -> Any:
    """Extract a field from dataclass, dict, sqlite3.Row, or generic object."""
    if isinstance(obj, Mapping):
        if key not in obj:
            raise DomainError("VALIDATION", 422)
        return obj[key]
    if isinstance(obj, sqlite3.Row):
        try:
            return obj[key]
        except (IndexError, KeyError):
            raise DomainError("VALIDATION", 422)
    if hasattr(obj, key):
        return getattr(obj, key)
    raise DomainError("VALIDATION", 422)


def post_entry(
    conn: sqlite3.Connection,
    *,
    term_id: int,
    entry_date: str,
    source_type: str,
    source_id: int,
    source_event: str,
    memo: str | None,
    lines: Sequence[Line],
    reverses_entry_id: int | None = None,
    adjusts_term_id: int | None = None,
) -> int:
    """Post a balanced journal entry idempotently.

    Uses DRAFT -> insert lines -> POSTED status transition.
    If the unique key (source_type, source_id, source_event) already exists:
      - If existing financial lines match requested lines, returns existing entry id.
      - If existing financial lines differ, raises DomainError("VALIDATION", 422).
    """
    if not lines or len(lines) < 2:
        raise DomainError("VALIDATION", 422)

    # Validate each line strictly
    validated_lines: list[tuple[str, int, int]] = []
    for l in lines:
        if not hasattr(l, "account_code") or not isinstance(l.account_code, str):
            raise DomainError("VALIDATION", 422)
        debit = _validate_paise(l.debit_paise)
        credit = _validate_paise(l.credit_paise)
        if (debit == 0) == (credit == 0):
            raise DomainError("VALIDATION", 422)
        validated_lines.append((l.account_code, debit, credit))

    total_debit = sum(vl[1] for vl in validated_lines)
    total_credit = sum(vl[2] for vl in validated_lines)
    if total_debit != total_credit or total_debit <= 0:
        raise DomainError("VALIDATION", 422)

    # 1. Check existing entry for source key idempotency
    cur = conn.execute(
        """
        SELECT id, term_id, status, reverses_entry_id, adjusts_term_id
        FROM journal_entries
        WHERE source_type = ? AND source_id = ? AND source_event = ?
        """,
        (source_type, source_id, source_event),
    )
    existing = cur.fetchone()
    if existing:
        existing_id = int(existing[0])
        lines_cur = conn.execute(
            """
            SELECT a.code, jl.debit_paise, jl.credit_paise
            FROM journal_lines jl
            JOIN accounts a ON a.id = jl.account_id
            WHERE jl.entry_id = ?
            ORDER BY jl.id ASC
            """,
            (existing_id,),
        )
        existing_lines = [(r[0], r[1], r[2]) for r in lines_cur.fetchall()]

        # Compare sorted by account_code, debit, credit without loose coercion
        if sorted(existing_lines) != sorted(validated_lines):
            raise DomainError("VALIDATION", 422)

        return existing_id

    now_ts = clock.now()
    created_at = now_ts
    posted_at = now_ts

    try:
        # Insert as DRAFT
        insert_cur = conn.execute(
            """
            INSERT INTO journal_entries (
                term_id, entry_date, source_type, source_id, source_event,
                memo, status, posted_at, reverses_entry_id, adjusts_term_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'DRAFT', NULL, ?, ?, ?)
            """,
            (
                term_id,
                entry_date,
                source_type,
                source_id,
                source_event,
                memo,
                reverses_entry_id,
                adjusts_term_id,
                created_at,
            ),
        )
        entry_id = int(insert_cur.lastrowid)

        # Insert lines
        for code, debit, credit in validated_lines:
            acc_id = _get_account_id(conn, code)
            conn.execute(
                """
                INSERT INTO journal_lines (entry_id, account_id, debit_paise, credit_paise, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (entry_id, acc_id, debit, credit, created_at),
            )

        # Flip to POSTED
        conn.execute(
            """
            UPDATE journal_entries
            SET status = 'POSTED', posted_at = ?
            WHERE id = ?
            """,
            (posted_at, entry_id),
        )
        return entry_id

    except sqlite3.IntegrityError as err:
        err_msg = str(err).lower()
        if "term_closed" in err_msg or "closed" in err_msg:
            raise DomainError("TERM_CLOSED", 409) from err
        raise DomainError("VALIDATION", 422) from err


def reverse_entry(conn: sqlite3.Connection, entry_id: int, memo: str) -> int:
    """Reverse an existing POSTED journal entry exactly once.

    Posts an exact mirror in the current OPEN term with lines swapped.
    Source event is '<original_source_event>_reversal'.
    Reversing twice raises DomainError("REFUND_BLOCKED", 409).
    """
    cur = conn.execute(
        """
        SELECT id, term_id, source_type, source_id, source_event, status, reverses_entry_id
        FROM journal_entries
        WHERE id = ?
        """,
        (entry_id,),
    )
    orig = cur.fetchone()
    if not orig:
        raise DomainError("NOT_FOUND", 404)

    orig_id, orig_term_id, s_type, s_id, s_event, status, reverses_id = orig
    if status != "POSTED":
        raise DomainError("VALIDATION", 422)

    # Exclude reversing a reversal entry
    if s_event.endswith("_reversal") or reverses_id is not None:
        raise DomainError("REFUND_BLOCKED", 409)

    # Check if already reversed
    check_cur = conn.execute(
        "SELECT id FROM journal_entries WHERE reverses_entry_id = ?",
        (orig_id,),
    )
    rev_row = check_cur.fetchone()
    if rev_row:
        raise DomainError("REFUND_BLOCKED", 409)

    # Fetch original lines
    lines_cur = conn.execute(
        """
        SELECT a.code, jl.debit_paise, jl.credit_paise
        FROM journal_lines jl
        JOIN accounts a ON a.id = jl.account_id
        WHERE jl.entry_id = ?
        ORDER BY jl.id ASC
        """,
        (orig_id,),
    )
    orig_lines = lines_cur.fetchall()
    if not orig_lines:
        raise DomainError("VALIDATION", 422)

    # Swap debits and credits
    mirror_lines = [
        Line(account_code=r[0], debit_paise=r[2], credit_paise=r[1])
        for r in orig_lines
    ]

    open_term_id = _get_open_term_id(conn)
    now_ts = clock.now()
    reversal_source_event = f"{s_event}_reversal"

    return post_entry(
        conn,
        term_id=open_term_id,
        entry_date=now_ts,
        source_type=s_type,
        source_id=s_id,
        source_event=reversal_source_event,
        memo=memo,
        lines=mirror_lines,
        reverses_entry_id=orig_id,
    )


def reverse_all_for_source(conn: sqlite3.Connection, source_type: str, source_id: int, memo: str) -> list[int]:
    """Reverse every not-yet-reversed entry for a given source, newest first.

    Refund source enumeration excludes reversal entries so retries cannot reverse a reversal.
    """
    cur = conn.execute(
        """
        SELECT e.id
        FROM journal_entries e
        LEFT JOIN journal_entries r ON r.reverses_entry_id = e.id
        WHERE e.source_type = ?
          AND e.source_id = ?
          AND e.status = 'POSTED'
          AND e.source_event NOT LIKE '%_reversal'
          AND e.reverses_entry_id IS NULL
          AND r.id IS NULL
        ORDER BY e.id DESC
        """,
        (source_type, source_id),
    )
    unreversed_ids = [int(row[0]) for row in cur.fetchall()]
    reversed_entry_ids: list[int] = []
    for eid in unreversed_ids:
        rev_id = reverse_entry(conn, eid, memo)
        reversed_entry_ids.append(rev_id)
    return reversed_entry_ids


def post_payment_received(conn: sqlite3.Connection, payment: Any, *, fulfilled: bool) -> int:
    """Post payment received entry (CONTRACT §7).

    Debit: 1100 Clearing
    Credit:
      - If fulfilled: purpose income account:
          DUES -> 4000
          TICKET -> 4100
          MERCH -> 4200
      - If unfulfilled: 2000 (Unfulfilled Payments Obligation)
    """
    p_id = _extract_field(payment, "id")
    p_amount = _validate_paise(_extract_field(payment, "amount_paise"))
    p_purpose = _extract_field(payment, "purpose")

    purpose_str = str(p_purpose).upper()
    if purpose_str not in {"DUES", "TICKET", "MERCH"}:
        raise DomainError("VALIDATION", 422)

    if fulfilled:
        purpose_account_map = {
            "DUES": "4000",
            "TICKET": "4100",
            "MERCH": "4200",
        }
        credit_code = purpose_account_map[purpose_str]
    else:
        credit_code = "2000"

    open_term_id = _get_open_term_id(conn)
    now_ts = clock.now()

    lines = [
        Line(account_code="1100", debit_paise=p_amount, credit_paise=0),
        Line(account_code=credit_code, debit_paise=0, credit_paise=p_amount),
    ]

    return post_entry(
        conn,
        term_id=open_term_id,
        entry_date=now_ts,
        source_type="payment",
        source_id=p_id,
        source_event="received",
        memo=f"Payment {p_id} received ({'fulfilled' if fulfilled else 'unfulfilled'})",
        lines=lines,
    )


def post_payment_late_fulfilled(conn: sqlite3.Connection, payment: Any) -> int:
    """Post obligation fulfillment for late-fulfilled payment (CONTRACT §7).

    Debit: 2000 Unfulfilled Obligation
    Credit: 4000 / 4100 / 4200 based on purpose
    """
    p_id = _extract_field(payment, "id")
    p_amount = _validate_paise(_extract_field(payment, "amount_paise"))
    p_purpose = _extract_field(payment, "purpose")

    purpose_str = str(p_purpose).upper()
    if purpose_str not in {"DUES", "TICKET", "MERCH"}:
        raise DomainError("VALIDATION", 422)

    purpose_account_map = {
        "DUES": "4000",
        "TICKET": "4100",
        "MERCH": "4200",
    }
    credit_code = purpose_account_map[purpose_str]

    open_term_id = _get_open_term_id(conn)
    now_ts = clock.now()

    lines = [
        Line(account_code="2000", debit_paise=p_amount, credit_paise=0),
        Line(account_code=credit_code, debit_paise=0, credit_paise=p_amount),
    ]

    return post_entry(
        conn,
        term_id=open_term_id,
        entry_date=now_ts,
        source_type="payment",
        source_id=p_id,
        source_event="fulfilled_late",
        memo=f"Payment {p_id} obligation fulfilled late",
        lines=lines,
    )


def post_receipt_event(conn: sqlite3.Connection, event_row: Any) -> int | None:
    """Post journal entry for unapplied receipt event (CONTRACT §3.1, §7).

    If currency is INR and amount > 0:
      Debit: 1100 Clearing
      Credit: 2000 Unfulfilled Payments Obligation
    Otherwise None.
    """
    e_id = _extract_field(event_row, "id")
    raw_amount = _extract_field(event_row, "amount_paise")
    if isinstance(raw_amount, bool) or not isinstance(raw_amount, int):
        raise DomainError("VALIDATION", 422)
    e_amount = raw_amount
    e_currency = _extract_field(event_row, "currency")

    if e_currency != "INR" or e_amount <= 0:
        return None

    open_term_id = _get_open_term_id(conn)
    now_ts = clock.now()

    lines = [
        Line(account_code="1100", debit_paise=e_amount, credit_paise=0),
        Line(account_code="2000", debit_paise=0, credit_paise=e_amount),
    ]

    return post_entry(
        conn,
        term_id=open_term_id,
        entry_date=now_ts,
        source_type="payment_event",
        source_id=e_id,
        source_event="received",
        memo=f"Unapplied receipt event {e_id} booked to clearing/obligation",
        lines=lines,
    )


def post_settlement(conn: sqlite3.Connection, source_type: str, source_id: int, amount_paise: int) -> int:
    """Post settlement entry for payment or payment_event (CONTRACT §7).

    Debit: 1000 Cash on Hand/Bank
    Credit: 1100 Payment Clearing
    """
    valid_amount = _validate_paise(amount_paise)
    if valid_amount <= 0:
        raise DomainError("VALIDATION", 422)

    open_term_id = _get_open_term_id(conn)
    now_ts = clock.now()

    lines = [
        Line(account_code="1000", debit_paise=valid_amount, credit_paise=0),
        Line(account_code="1100", debit_paise=0, credit_paise=valid_amount),
    ]

    return post_entry(
        conn,
        term_id=open_term_id,
        entry_date=now_ts,
        source_type=source_type,
        source_id=source_id,
        source_event="settled",
        memo=f"Settlement for {source_type} {source_id}",
        lines=lines,
    )


def post_expense_approved(conn: sqlite3.Connection, expense: Any) -> int:
    """Post approved expense entry (CONTRACT §7).

    Debit: Category account (5000-5099)
    Credit: 2100 Reimbursements Payable
    """
    exp_id = _extract_field(expense, "id")
    exp_amount = _validate_paise(_extract_field(expense, "amount_paise"))
    if exp_amount <= 0:
        raise DomainError("VALIDATION", 422)

    try:
        cat_code = _extract_field(expense, "category_code")
    except DomainError:
        cat_code = None

    if not cat_code:
        cat_acc_id = _extract_field(expense, "category_account_id")
        cur = conn.execute("SELECT code FROM accounts WHERE id = ?", (cat_acc_id,))
        row = cur.fetchone()
        if not row:
            raise DomainError("VALIDATION", 422)
        cat_code = row[0]

    if not (cat_code.startswith("50") and len(cat_code) == 4):
        raise DomainError("VALIDATION", 422)

    open_term_id = _get_open_term_id(conn)
    now_ts = clock.now()

    lines = [
        Line(account_code=cat_code, debit_paise=exp_amount, credit_paise=0),
        Line(account_code="2100", debit_paise=0, credit_paise=exp_amount),
    ]

    return post_entry(
        conn,
        term_id=open_term_id,
        entry_date=now_ts,
        source_type="expense",
        source_id=exp_id,
        source_event="approved",
        memo=f"Expense {exp_id} approved",
        lines=lines,
    )


def post_expense_paid(conn: sqlite3.Connection, expense: Any) -> int:
    """Post paid expense entry (CONTRACT §7).

    Debit: 2100 Reimbursements Payable
    Credit: 1000 Cash on Hand/Bank
    """
    exp_id = _extract_field(expense, "id")
    exp_amount = _validate_paise(_extract_field(expense, "amount_paise"))
    if exp_amount <= 0:
        raise DomainError("VALIDATION", 422)

    open_term_id = _get_open_term_id(conn)
    now_ts = clock.now()

    lines = [
        Line(account_code="2100", debit_paise=exp_amount, credit_paise=0),
        Line(account_code="1000", debit_paise=0, credit_paise=exp_amount),
    ]

    return post_entry(
        conn,
        term_id=open_term_id,
        entry_date=now_ts,
        source_type="expense",
        source_id=exp_id,
        source_event="paid",
        memo=f"Expense {exp_id} paid",
        lines=lines,
    )
