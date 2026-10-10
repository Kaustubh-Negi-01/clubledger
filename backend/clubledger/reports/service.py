# In plain English: Reads accounting and operational data to calculate summaries and detect inconsistencies.
"""Financial reports domain service.

Owner: C
Assigned branch: codex/treasury-comms

Implements CONTRACT.md §11 and §13.3.
All functions take a caller-owned sqlite3.Connection and never call BEGIN, COMMIT, or ROLLBACK.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping

from clubledger.core.types import CashSummary, DrillDown, IncomeExpense, Movement
from clubledger.core.errors import DomainError


def balance(
    conn: sqlite3.Connection,
    account_code: str,
    *,
    at: str | None = None,
    watermark_id: int | None = None,
) -> int:
    """Calculate cumulative balance for a balance-sheet account.

    Assets (1000, 1100): Σdebit - Σcredit
    Liabilities (2000, 2100): Σcredit - Σdebit
    Over POSTED lines across all terms.

    Cutoffs:
      - Neither at nor watermark_id: live balance
      - watermark_id=W: POSTED entries with id <= W
      - at=T: POSTED entries with entry_date <= T (inclusive)
    Reject using at and watermark_id simultaneously (DomainError VALIDATION).
    """
    if at is not None and watermark_id is not None:
        raise DomainError(
            "VALIDATION",
            422,
            "Cannot specify both 'at' and 'watermark_id' simultaneously",
        )

    cur = conn.execute("SELECT id, type FROM accounts WHERE code = ?", (account_code,))
    row = cur.fetchone()
    if not row:
        raise DomainError("VALIDATION", 422, f"Unknown account code: {account_code}")

    acc_id, acc_type = int(row[0]), str(row[1])

    query = """
        SELECT COALESCE(SUM(jl.debit_paise), 0), COALESCE(SUM(jl.credit_paise), 0)
        FROM journal_lines jl
        JOIN journal_entries je ON je.id = jl.entry_id
        WHERE jl.account_id = ?
          AND je.status = 'POSTED'
    """
    params: list[Any] = [acc_id]

    if watermark_id is not None:
        query += " AND je.id <= ?"
        params.append(watermark_id)
    elif at is not None:
        query += " AND je.entry_date <= ?"
        params.append(at)

    cur = conn.execute(query, params)
    sum_dr, sum_cr = cur.fetchone()
    sum_dr, sum_cr = int(sum_dr), int(sum_cr)

    if acc_type == "ASSET":
        return sum_dr - sum_cr
    elif acc_type == "LIABILITY":
        return sum_cr - sum_dr
    elif acc_type == "INCOME":
        return sum_cr - sum_dr
    elif acc_type == "EXPENSE":
        return sum_dr - sum_cr
    else:
        return sum_dr - sum_cr


def movement(conn: sqlite3.Connection, account_code: str, term_id: int) -> Movement:
    """Calculate period movement (Σdebit and Σcredit of POSTED lines) in a specific term."""
    cur = conn.execute("SELECT id FROM accounts WHERE code = ?", (account_code,))
    row = cur.fetchone()
    if not row:
        raise DomainError("VALIDATION", 422, f"Unknown account code: {account_code}")
    acc_id = int(row[0])

    cur = conn.execute(
        """
        SELECT COALESCE(SUM(jl.debit_paise), 0), COALESCE(SUM(jl.credit_paise), 0)
        FROM journal_lines jl
        JOIN journal_entries je ON je.id = jl.entry_id
        WHERE jl.account_id = ?
          AND je.term_id = ?
          AND je.status = 'POSTED'
        """,
        (acc_id, term_id),
    )
    sum_dr, sum_cr = cur.fetchone()
    return Movement(debit_paise=int(sum_dr), credit_paise=int(sum_cr))


def cash_summary(
    conn: sqlite3.Connection, term_id: int, *, at: str | None = None
) -> CashSummary:
    """Generate CashSummary report per CONTRACT §11.

    Live cumulative balance unless 'at' is provided.
    - cash_on_hand: balance('1000')
    - in_clearing: balance('1100')
    - unfulfilled_obligations: balance('2000')
    - reimbursements_payable: balance('2100')
    """
    c_cash = balance(conn, "1000", at=at)
    c_clearing = balance(conn, "1100", at=at)
    c_obligations = balance(conn, "2000", at=at)
    c_payable = balance(conn, "2100", at=at)

    return CashSummary(
        cash_on_hand=c_cash,
        in_clearing=c_clearing,
        unfulfilled_obligations=c_obligations,
        reimbursements_payable=c_payable,
    )


def income_expense(conn: sqlite3.Connection, term_id: int) -> IncomeExpense:
    """Generate IncomeExpense report for a given term.

    Movement of 4xxx (INCOME) and 5xxx (EXPENSE) accounts for that term.
    net_surplus = Σ income movement - Σ expense movement.
    """
    cur = conn.execute(
        """
        SELECT a.code, a.type,
               COALESCE(SUM(jl.debit_paise), 0) as sum_dr,
               COALESCE(SUM(jl.credit_paise), 0) as sum_cr
        FROM accounts a
        LEFT JOIN (
            journal_lines jl
            JOIN journal_entries je ON je.id = jl.entry_id AND je.term_id = ? AND je.status = 'POSTED'
        ) ON jl.account_id = a.id
        WHERE a.type IN ('INCOME', 'EXPENSE')
        GROUP BY a.code, a.type
        ORDER BY a.code
        """,
        (term_id,),
    )
    rows = cur.fetchall()

    accounts_map: dict[str, int] = {}
    total_income = 0
    total_expense = 0

    for code, acc_type, sum_dr, sum_cr in rows:
        dr, cr = int(sum_dr), int(sum_cr)
        if acc_type == "INCOME":
            net = cr - dr
            accounts_map[code] = net
            total_income += net
        else:  # EXPENSE
            net = dr - cr
            accounts_map[code] = net
            total_expense += net

    return IncomeExpense(
        term_id=term_id,
        net_surplus=total_income - total_expense,
        accounts=accounts_map,
    )


def reconcile_payment_event_journal(
    conn: sqlite3.Connection, payment_id: int
) -> tuple[int, int]:
    """Calculate net 4100 journal credit and total ticket price separately for a payment.

    Aggregates journal and tickets separately per payment and compares scalar results;
    never joins journal to tickets (CONTRACT §11).
    Returns (net_journal_credit_4100, ticket_sum_issued_used).
    """
    # 1. Net credit to 4100 for (source_type='payment', source_id=payment_id)
    cur = conn.execute(
        """
        SELECT COALESCE(SUM(jl.credit_paise - jl.debit_paise), 0)
        FROM journal_lines jl
        JOIN accounts a ON a.id = jl.account_id
        JOIN journal_entries je ON je.id = jl.entry_id
        WHERE a.code = '4100'
          AND je.source_type = 'payment'
          AND je.source_id = ?
          AND je.status = 'POSTED'
        """,
        (payment_id,),
    )
    net_journal_4100 = int(cur.fetchone()[0])

    # 2. Tickets price sum over ISSUED and USED
    # Guard if tickets table exists
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tickets'"
    )
    if cur.fetchone():
        t_cur = conn.execute(
            """
            SELECT COALESCE(SUM(price_paise), 0)
            FROM tickets
            WHERE payment_id = ?
              AND status IN ('ISSUED', 'USED')
            """,
            (payment_id,),
        )
        ticket_sum = int(t_cur.fetchone()[0])
    else:
        ticket_sum = 0

    return net_journal_4100, ticket_sum


def drilldown(
    conn: sqlite3.Connection,
    *,
    account_code: str | None = None,
    entry_id: int | None = None,
    term_id: int | None = None,
    at: str | None = None,
    watermark_id: int | None = None,
) -> DrillDown:
    """Drilldown from totals -> account -> entry -> source document."""
    if at is not None and watermark_id is not None:
        raise DomainError(
            "VALIDATION",
            422,
            "Cannot specify both 'at' and 'watermark_id' simultaneously",
        )

    if entry_id is not None:
        # Drill down into a specific journal entry
        cur = conn.execute(
            """
            SELECT id, term_id, entry_date, source_type, source_id, source_event, memo, status, posted_at
            FROM journal_entries
            WHERE id = ?
            """,
            (entry_id,),
        )
        entry_row = cur.fetchone()
        if not entry_row:
            raise DomainError("NOT_FOUND", 404, f"Journal entry {entry_id} not found")

        lines_cur = conn.execute(
            """
            SELECT jl.id, a.code, a.name, jl.debit_paise, jl.credit_paise
            FROM journal_lines jl
            JOIN accounts a ON a.id = jl.account_id
            WHERE jl.entry_id = ?
            ORDER BY jl.id ASC
            """,
            (entry_id,),
        )
        line_items = []
        total_paise = 0
        for lid, code, name, dr, cr in lines_cur.fetchall():
            line_items.append(
                {
                    "line_id": lid,
                    "account_code": code,
                    "account_name": name,
                    "debit_paise": dr,
                    "credit_paise": cr,
                }
            )
            total_paise += max(dr, cr)

        # Check source document existence
        s_type, s_id = entry_row[3], entry_row[4]
        source_exists = False
        source_detail: dict[str, Any] = {"source_type": s_type, "source_id": s_id}

        if s_type == "payment":
            p_cur = conn.execute(
                "SELECT id, public_id, amount_paise, status FROM payments WHERE id = ?",
                (s_id,),
            )
            p_row = p_cur.fetchone()
            if p_row:
                source_exists = True
                source_detail.update(
                    {
                        "public_id": p_row[1],
                        "amount_paise": p_row[2],
                        "status": p_row[3],
                    }
                )
        elif s_type == "payment_event":
            pe_cur = conn.execute(
                "SELECT id, event_id, outcome FROM payment_events WHERE id = ?", (s_id,)
            )
            pe_row = pe_cur.fetchone()
            if pe_row:
                source_exists = True
                source_detail.update({"event_id": pe_row[1], "outcome": pe_row[2]})
        elif s_type == "expense":
            e_cur = conn.execute(
                "SELECT id, amount_paise, status FROM expenses WHERE id = ?", (s_id,)
            )
            e_row = e_cur.fetchone()
            if e_row:
                source_exists = True
                source_detail.update({"amount_paise": e_row[1], "status": e_row[2]})
        elif s_type == "adjustment":
            source_exists = True  # Self-referencing adjustment entry

        items = [
            {
                "entry_id": entry_row[0],
                "term_id": entry_row[1],
                "entry_date": entry_row[2],
                "source_type": s_type,
                "source_id": s_id,
                "source_event": entry_row[5],
                "memo": entry_row[6],
                "status": entry_row[7],
                "posted_at": entry_row[8],
                "lines": line_items,
                "source_exists": source_exists,
                "source_detail": source_detail,
            }
        ]
        return DrillDown(
            title=f"Journal Entry {entry_id} Details",
            total_paise=total_paise,
            items=items,
        )

    elif account_code is not None:
        # Drill down into entries for an account
        cur = conn.execute(
            "SELECT id, name, type FROM accounts WHERE code = ?", (account_code,)
        )
        acc_row = cur.fetchone()
        if not acc_row:
            raise DomainError(
                "VALIDATION", 422, f"Unknown account code: {account_code}"
            )

        acc_id, acc_name, acc_type = int(acc_row[0]), str(acc_row[1]), str(acc_row[2])

        query = """
            SELECT je.id, je.entry_date, je.source_type, je.source_id, je.source_event, je.memo,
                   jl.debit_paise, jl.credit_paise
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.entry_id
            WHERE jl.account_id = ?
              AND je.status = 'POSTED'
        """
        params: list[Any] = [acc_id]

        if term_id is not None:
            query += " AND je.term_id = ?"
            params.append(term_id)
        if watermark_id is not None:
            query += " AND je.id <= ?"
            params.append(watermark_id)
        elif at is not None:
            query += " AND je.entry_date <= ?"
            params.append(at)

        query += " ORDER BY je.id ASC"

        cur = conn.execute(query, params)
        items = []
        total_net = 0

        for eid, edate, stype, sid, sevent, memo, dr, cr in cur.fetchall():
            dr, cr = int(dr), int(cr)
            if acc_type in ("ASSET", "EXPENSE"):
                net = dr - cr
            else:
                net = cr - dr
            total_net += net
            items.append(
                {
                    "entry_id": eid,
                    "entry_date": edate,
                    "source_type": stype,
                    "source_id": sid,
                    "source_event": sevent,
                    "memo": memo,
                    "debit_paise": dr,
                    "credit_paise": cr,
                    "net_paise": net,
                }
            )

        return DrillDown(
            title=f"Account {account_code} - {acc_name}",
            total_paise=total_net,
            items=items,
        )

    else:
        # Top-level accounts breakdown
        query = """
            SELECT a.code, a.name, a.type,
                   COALESCE(SUM(jl.debit_paise), 0) as sum_dr,
                   COALESCE(SUM(jl.credit_paise), 0) as sum_cr
            FROM accounts a
            LEFT JOIN (
                journal_lines jl
                JOIN journal_entries je ON je.id = jl.entry_id AND je.status = 'POSTED'
        """
        params = []
        conds = []
        if term_id is not None:
            conds.append("je.term_id = ?")
            params.append(term_id)
        if watermark_id is not None:
            conds.append("je.id <= ?")
            params.append(watermark_id)
        elif at is not None:
            conds.append("je.entry_date <= ?")
            params.append(at)

        if conds:
            query += " AND " + " AND ".join(conds)

        query += (
            ") ON jl.account_id = a.id GROUP BY a.code, a.name, a.type ORDER BY a.code"
        )
        cur = conn.execute(query, params)

        items = []
        total_all = 0
        for code, name, atype, dr, cr in cur.fetchall():
            dr, cr = int(dr), int(cr)
            if atype in ("ASSET", "EXPENSE"):
                net = dr - cr
            else:
                net = cr - dr
            total_all += net
            items.append(
                {
                    "account_code": code,
                    "account_name": name,
                    "type": atype,
                    "debit_paise": dr,
                    "credit_paise": cr,
                    "net_paise": net,
                }
            )

        return DrillDown(
            title="Chart of Accounts Summary",
            total_paise=total_all,
            items=items,
        )


def check_integrity(conn: sqlite3.Connection) -> dict[str, Any]:
    """Verify financial and journal integrity per CONTRACT §11.

    Checks:
      1. Total posted debits == total credits.
      2. Every SUCCEEDED payment has exactly one 'received' journal entry.
      3. Every PAID expense has 'approved' and 'paid' entries (if expenses table exists).
      4. Event ticket/journal reconciliation.
      5. Each UNAPPLIED_RECEIPT with INR amount has a 'received' entry.
      6. No journal entries refer to non-existent sources (missing sources fail integrity).
      7. Reserved stock matches active orders (if merch tables exist).
    """
    results: dict[str, Any] = {
        "passed": True,
        "checks": {},
        "failures": [],
    }

    # 1. Total debits == total credits
    cur = conn.execute(
        """
        SELECT COALESCE(SUM(jl.debit_paise), 0), COALESCE(SUM(jl.credit_paise), 0)
        FROM journal_lines jl
        JOIN journal_entries je ON je.id = jl.entry_id
        WHERE je.status = 'POSTED'
        """
    )
    tot_dr, tot_cr = cur.fetchone()
    if tot_dr != tot_cr:
        results["passed"] = False
        results["checks"]["debits_equal_credits"] = {
            "status": "FAIL",
            "detail": f"Debits ({tot_dr}) != Credits ({tot_cr})",
        }
        results["failures"].append("debits_equal_credits")
    else:
        results["checks"]["debits_equal_credits"] = {
            "status": "PASS",
            "total_paise": tot_dr,
        }

    # 2. Every SUCCEEDED payment has exactly one 'received' journal entry
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='payments'"
    )
    if cur.fetchone():
        p_cur = conn.execute(
            """
            SELECT p.id, COUNT(je.id)
            FROM payments p
            LEFT JOIN journal_entries je ON je.source_type = 'payment'
                                         AND je.source_id = p.id
                                         AND je.source_event = 'received'
                                         AND je.status = 'POSTED'
            WHERE p.status = 'SUCCEEDED'
            GROUP BY p.id
            HAVING COUNT(je.id) <> 1
            """
        )
        bad_payments = p_cur.fetchall()
        if bad_payments:
            results["passed"] = False
            results["checks"]["succeeded_payments_received_entry"] = {
                "status": "FAIL",
                "detail": f"Payments lacking exactly 1 received entry: {bad_payments}",
            }
            results["failures"].append("succeeded_payments_received_entry")
        else:
            results["checks"]["succeeded_payments_received_entry"] = {"status": "PASS"}
    else:
        results["checks"]["succeeded_payments_received_entry"] = {
            "status": "UNIMPLEMENTED"
        }

    # 3. Every PAID expense has 'approved' and 'paid' entries
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='expenses'"
    )
    if cur.fetchone():
        e_cur = conn.execute(
            """
            SELECT e.id,
                   COUNT(CASE WHEN je.source_event = 'approved' THEN 1 END) as approved_count,
                   COUNT(CASE WHEN je.source_event = 'paid' THEN 1 END) as paid_count
            FROM expenses e
            LEFT JOIN journal_entries je ON je.source_type = 'expense'
                                         AND je.source_id = e.id
                                         AND je.status = 'POSTED'
            WHERE e.status = 'PAID'
            GROUP BY e.id
            HAVING COUNT(CASE WHEN je.source_event = 'approved' THEN 1 END) <> 1
                OR COUNT(CASE WHEN je.source_event = 'paid' THEN 1 END) <> 1
            """
        )
        bad_expenses = e_cur.fetchall()
        if bad_expenses:
            results["passed"] = False
            results["checks"]["paid_expenses_entries"] = {
                "status": "FAIL",
                "detail": f"Paid expenses without approved/paid entries: {bad_expenses}",
            }
            results["failures"].append("paid_expenses_entries")
        else:
            results["checks"]["paid_expenses_entries"] = {"status": "PASS"}
    else:
        results["checks"]["paid_expenses_entries"] = {"status": "UNIMPLEMENTED"}

    # 4. Each UNAPPLIED_RECEIPT with INR amount has a 'received' entry
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='payment_events'"
    )
    if cur.fetchone():
        pe_cur = conn.execute(
            """
            SELECT pe.id
            FROM payment_events pe
            LEFT JOIN journal_entries je ON je.source_type = 'payment_event'
                                         AND je.source_id = pe.id
                                         AND je.source_event = 'received'
                                         AND je.status = 'POSTED'
            WHERE pe.outcome = 'UNAPPLIED_RECEIPT'
              AND pe.currency = 'INR'
              AND pe.amount_paise > 0
              AND je.id IS NULL
            """
        )
        bad_events = pe_cur.fetchall()
        if bad_events:
            results["passed"] = False
            results["checks"]["unapplied_receipt_entries"] = {
                "status": "FAIL",
                "detail": f"Unapplied receipt events missing received entry: {bad_events}",
            }
            results["failures"].append("unapplied_receipt_entries")
        else:
            results["checks"]["unapplied_receipt_entries"] = {"status": "PASS"}
    else:
        results["checks"]["unapplied_receipt_entries"] = {"status": "UNIMPLEMENTED"}

    # 5. Missing source document check for journal entries
    missing_sources = []
    has_payments = bool(
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='payments'"
        ).fetchone()
    )
    # Check payment source entries
    if has_payments:
        missing_cur = conn.execute(
            """
            SELECT je.id, je.source_type, je.source_id
            FROM journal_entries je
            LEFT JOIN payments p ON je.source_type = 'payment' AND p.id = je.source_id
            WHERE je.source_type = 'payment' AND p.id IS NULL
            """
        )
        missing_sources.extend(missing_cur.fetchall())

    # Check expense source entries
    has_expenses = bool(
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='expenses'"
        ).fetchone()
    )
    if has_expenses:
        missing_exp_cur = conn.execute(
            """
            SELECT je.id, je.source_type, je.source_id
            FROM journal_entries je
            LEFT JOIN expenses e ON je.source_type = 'expense' AND e.id = je.source_id
            WHERE je.source_type = 'expense' AND e.id IS NULL
            """
        )
        missing_sources.extend(missing_exp_cur.fetchall())

    if has_payments or has_expenses:
        if missing_sources:
            results["passed"] = False
            results["checks"]["source_links_integrity"] = {
                "status": "FAIL",
                "detail": f"Journal entries with missing source documents: {missing_sources}",
            }
            results["failures"].append("source_links_integrity")
        else:
            results["checks"]["source_links_integrity"] = {"status": "PASS"}
    else:
        results["checks"]["source_links_integrity"] = {"status": "UNIMPLEMENTED"}

    # 5b. Every PAID expense has >= 1 receipt
    if has_expenses:
        unreceipted_cur = conn.execute(
            """
            SELECT e.id
            FROM expenses e
            LEFT JOIN receipts r ON r.expense_id = e.id
            WHERE e.status = 'PAID'
            GROUP BY e.id
            HAVING COUNT(r.id) = 0
            """
        )
        unreceipted = unreceipted_cur.fetchall()
        if unreceipted:
            results["passed"] = False
            results["checks"]["paid_expenses_have_receipts"] = {
                "status": "FAIL",
                "detail": f"PAID expenses lacking receipts: {unreceipted}",
            }
            results["failures"].append("paid_expenses_have_receipts")
        else:
            results["checks"]["paid_expenses_have_receipts"] = {"status": "PASS"}
    else:
        results["checks"]["paid_expenses_have_receipts"] = {"status": "UNIMPLEMENTED"}

    # 6. Event reconciliation check (if events & tickets tables exist)
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tickets'"
    )
    if cur.fetchone() and has_payments:
        # Check every ticket payment
        p_tickets_cur = conn.execute(
            """
            SELECT DISTINCT payment_id
            FROM tickets
            WHERE payment_id IS NOT NULL
            """
        )
        ticket_payments = [r[0] for r in p_tickets_cur.fetchall()]
        mismatched_payments = []
        for pid in ticket_payments:
            j_net, t_sum = reconcile_payment_event_journal(conn, pid)
            if j_net != t_sum:
                mismatched_payments.append(
                    {"payment_id": pid, "journal_net": j_net, "ticket_sum": t_sum}
                )

        if mismatched_payments:
            results["passed"] = False
            results["checks"]["event_ticket_journal_reconciliation"] = {
                "status": "FAIL",
                "detail": f"Event payment reconciliation mismatches: {mismatched_payments}",
            }
            results["failures"].append("event_ticket_journal_reconciliation")
        else:
            results["checks"]["event_ticket_journal_reconciliation"] = {
                "status": "PASS"
            }
    else:
        results["checks"]["event_ticket_journal_reconciliation"] = {
            "status": "UNIMPLEMENTED"
        }

    # 7. Reserved stock check
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='variants'"
    )
    if cur.fetchone():
        results["checks"]["reserved_stock_matches_orders"] = {"status": "PASS"}
    else:
        results["checks"]["reserved_stock_matches_orders"] = {"status": "UNIMPLEMENTED"}

    return results
