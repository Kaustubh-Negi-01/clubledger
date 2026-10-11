# In plain English: Serves financial summaries, account entries and integrity results.
"""Finance and reports endpoints per CONTRACT.md §12.

Owner: C
Assigned branch: codex/treasury-comms

Routes:
  GET /finance
  GET /finance/accounts/{code}
  GET /finance/entries/{id}
  GET /finance/integrity
All protected by perm:finance.view.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from clubledger.config import get_db_path
from clubledger.security.auth import require_perm, get_user_permissions
from clubledger.core.db import connect
from clubledger.core.types import Session
from clubledger.reports import service

router = APIRouter(prefix="/finance", tags=["finance"])

from clubledger.paths import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


from clubledger.core.errors import DomainError


def _get_open_term_id(conn) -> int:
    cur = conn.execute("SELECT id FROM terms WHERE status = 'OPEN'")
    row = cur.fetchone()
    if row:
        return int(row[0])
    raise DomainError("TERM_CLOSED", 409, "No active OPEN term found")


@router.get("", response_class=HTMLResponse)
def get_finance_dashboard(
    request: Request,
    session: Annotated[Session, Depends(require_perm("finance.view"))],
    as_of: Annotated[str | None, Query(alias="as_of")] = None,
    period_id: Annotated[int | None, Query()] = None,
    account_search: Annotated[str, Query(max_length=80)] = "",
    account_type: Annotated[str, Query()] = "ALL",
    activity: Annotated[str, Query()] = "ALL",
) -> Response:
    """Handle GET . Get finance dashboard."""
    conn = connect(get_db_path())
    try:
        term_id = period_id or _get_open_term_id(conn)
        if not conn.execute("SELECT 1 FROM terms WHERE id=?", (term_id,)).fetchone():
            raise DomainError("NOT_FOUND", 404)
        cs = service.cash_summary(conn, term_id, at=as_of)
        bd = service.drilldown(conn, at=as_of)
        period_bd = service.drilldown(conn, term_id=term_id, at=as_of)
        period_accounts = {item["account_code"]: item for item in period_bd.items}
        for item in bd.items:
            if item["type"] in ("INCOME", "EXPENSE"):
                item.update(period_accounts[item["account_code"]])

        account_type = account_type.upper()
        activity = activity.upper()
        if account_type not in {"ALL", "ASSET", "LIABILITY", "INCOME", "EXPENSE"}:
            account_type = "ALL"
        if activity not in {"ALL", "NONZERO"}:
            activity = "ALL"
        normalized_search = account_search.strip().casefold()
        filtered_items = [
            item
            for item in bd.items
            if (
                not normalized_search
                or normalized_search in item["account_code"].casefold()
                or normalized_search in item["account_name"].casefold()
            )
            and (account_type == "ALL" or item["type"] == account_type)
            and (activity == "ALL" or item["net_paise"] != 0)
        ]

        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse(
                {
                    "cash_summary": {
                        "cash_on_hand": cs.cash_on_hand,
                        "in_clearing": cs.in_clearing,
                        "unfulfilled_obligations": cs.unfulfilled_obligations,
                        "reimbursements_payable": cs.reimbursements_payable,
                    },
                    "breakdown": filtered_items,
                }
            )

        return templates.TemplateResponse(
            request=request,
            name="finance/index.html",
            context={
                "title": "Finance & Treasury",
                "cash_summary": cs,
                "breakdown": bd,
                "filtered_breakdown": filtered_items,
                "account_search": account_search.strip(),
                "account_type": account_type,
                "activity": activity,
                "user": session,
                "period_id": term_id,
                "terms": conn.execute(
                    "SELECT id,label,status FROM terms ORDER BY id DESC"
                ).fetchall(),
            },
        )
    finally:
        conn.close()


@router.get("/accounts/{code}", response_class=HTMLResponse)
def get_account_drilldown(
    request: Request,
    code: str,
    session: Annotated[Session, Depends(require_perm("finance.view"))],
    as_of: Annotated[str | None, Query(alias="as_of")] = None,
    watermark_id: Annotated[int | None, Query(alias="watermark_id")] = None,
    period_id: Annotated[int | None, Query()] = None,
) -> Response:
    """Handle GET /accounts/{code}. Get account drilldown."""
    conn = connect(get_db_path())
    try:
        account = conn.execute(
            "SELECT type FROM accounts WHERE code=?", (code,)
        ).fetchone()
        term_id = (
            (period_id or _get_open_term_id(conn))
            if account and account["type"] in ("INCOME", "EXPENSE")
            else None
        )
        dd = service.drilldown(
            conn,
            account_code=code,
            term_id=term_id,
            at=as_of,
            watermark_id=watermark_id,
        )

        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse(
                {"title": dd.title, "total_paise": dd.total_paise, "items": dd.items}
            )

        return templates.TemplateResponse(
            request=request,
            name="finance/account.html",
            context={
                "drilldown": dd,
                "user": session,
            },
        )
    finally:
        conn.close()


@router.get("/entries/{entry_id}", response_class=HTMLResponse)
def get_entry_drilldown(
    request: Request,
    entry_id: int,
    session: Annotated[Session, Depends(require_perm("finance.view"))],
) -> Response:
    """Handle GET /entries/{entry_id}. Get entry drilldown."""
    conn = connect(get_db_path())
    try:
        dd = service.drilldown(conn, entry_id=entry_id)
        source = dd.items[0]
        source_expense = None
        source_receipts = []
        if source["source_type"] == "expense":
            source_expense = conn.execute(
                "SELECT e.*, f.title AS fundraiser_title FROM expenses e LEFT JOIN fundraisers f ON f.id=e.fundraiser_id WHERE e.id=?",
                (source["source_id"],),
            ).fetchone()
            if source_expense and (
                source_expense["submitter_id"] == session.user_id
                or "receipts.view_all" in get_user_permissions(conn, session.user_id)
            ):
                source_receipts = conn.execute(
                    "SELECT id,original_name FROM receipts WHERE expense_id=?",
                    (source["source_id"],),
                ).fetchall()

        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse(
                {"title": dd.title, "total_paise": dd.total_paise, "items": dd.items}
            )

        return templates.TemplateResponse(
            request=request,
            name="finance/entry.html",
            context={
                "drilldown": dd,
                "user": session,
                "source_expense": source_expense,
                "source_receipts": source_receipts,
            },
        )
    finally:
        conn.close()


@router.get("/integrity", response_class=HTMLResponse)
def get_integrity_page(
    request: Request,
    session: Annotated[Session, Depends(require_perm("finance.view"))],
) -> Response:
    """Handle GET /integrity. Get integrity page."""
    conn = connect(get_db_path())
    try:
        results = service.check_integrity(conn)

        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse(results)

        return templates.TemplateResponse(
            request=request,
            name="finance/integrity.html",
            context={
                "integrity": results,
                "user": session,
            },
        )
    finally:
        conn.close()
