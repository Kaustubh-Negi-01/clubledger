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
from clubledger.core.auth import require_perm
from clubledger.core.db import connect
from clubledger.core.types import Session
from clubledger.reports import service

router = APIRouter(prefix="/finance", tags=["finance"])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
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
) -> Response:
    conn = connect(get_db_path())
    try:
        term_id = _get_open_term_id(conn)
        cs = service.cash_summary(conn, term_id, at=as_of)
        bd = service.drilldown(conn, at=as_of)

        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse(
                {
                    "cash_summary": {
                        "cash_on_hand": cs.cash_on_hand,
                        "in_clearing": cs.in_clearing,
                        "unfulfilled_obligations": cs.unfulfilled_obligations,
                        "reimbursements_payable": cs.reimbursements_payable,
                    },
                    "breakdown": bd.items,
                }
            )

        return templates.TemplateResponse(
            request=request,
            name="finance/index.html",
            context={
                "title": "Finance & Treasury",
                "cash_summary": cs,
                "breakdown": bd,
                "user": session,
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
) -> Response:
    conn = connect(get_db_path())
    try:
        dd = service.drilldown(conn, account_code=code, at=as_of, watermark_id=watermark_id)

        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"title": dd.title, "total_paise": dd.total_paise, "items": dd.items})

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
    conn = connect(get_db_path())
    try:
        dd = service.drilldown(conn, entry_id=entry_id)

        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"title": dd.title, "total_paise": dd.total_paise, "items": dd.items})

        return templates.TemplateResponse(
            request=request,
            name="finance/entry.html",
            context={
                "drilldown": dd,
                "user": session,
            },
        )
    finally:
        conn.close()


@router.get("/integrity", response_class=HTMLResponse)
def get_integrity_page(
    request: Request,
    session: Annotated[Session, Depends(require_perm("finance.view"))],
) -> Response:
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
