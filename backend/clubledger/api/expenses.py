# In plain English: Accepts expense forms, receipt uploads and officer decisions.
"""Expenses and Receipts HTTP routes per CONTRACT.md §12.

Owner: C
Assigned branch: codex/treasury-comms

Routes:
  GET /expenses/new, GET /expenses, POST /expenses/new (auth, members)
  POST /expenses/{id}/receipt (auth, own)
  GET /receipts/{id} (owner or perm:receipts.view_all)
  POST /admin/expenses/{id}/approve|reject|pay (perm:expenses.approve / expenses.pay)
"""

from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from clubledger.config import get_db_path
from clubledger.security.auth import get_current_session, get_user_permissions, require_perm
from clubledger.security.csrf import verify_csrf_token
from clubledger.core.db import connect, unit_of_work
from clubledger.core.errors import DomainError
from clubledger.core.types import Session
from clubledger.expenses import service as expense_service
from clubledger.expenses.receipts import resolve_receipt_file

router = APIRouter(tags=["expenses"])

from clubledger.paths import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/expenses", response_class=HTMLResponse)
def list_expenses(
    request: Request,
    session: Annotated[Session, Depends(get_current_session)],
) -> Response:
    """Handle GET /expenses. List expenses."""
    with unit_of_work(get_db_path()) as conn:
        cur = conn.execute(
            """
            SELECT e.id, e.amount_paise, e.description, e.status, e.created_at, a.code as category_code
            FROM expenses e
            JOIN accounts a ON a.id = e.category_account_id
            WHERE e.submitter_id = ?
            ORDER BY e.id DESC
            """,
            (session.user_id,),
        )
        expenses = [
            dict(
                zip(
                    [
                        "id",
                        "amount_paise",
                        "description",
                        "status",
                        "created_at",
                        "category_code",
                    ],
                    r,
                )
            )
            for r in cur.fetchall()
        ]

    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"expenses": expenses})

    return templates.TemplateResponse(
        request=request,
        name="expenses/list.html",
        context={"expenses": expenses, "user": session},
    )


@router.post("/expenses/new")
def post_create_expense(
    request: Request,
    session: Annotated[Session, Depends(get_current_session)],
    category_account_id: Annotated[int, Form()],
    amount_paise: Annotated[int, Form()],
    description: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    event_id: Annotated[int | None, Form()] = None,
    fundraiser_id: Annotated[int | None, Form()] = None,
    task_id: Annotated[int | None, Form()] = None,
) -> Response:
    """Handle POST /expenses/new. Post create expense."""
    verify_csrf_token(session.csrf_token, csrf_token)

    with unit_of_work(get_db_path()) as conn:
        exp_id = expense_service.submit_expense(
            conn,
            submitter_id=session.user_id,
            category_account_id=category_account_id,
            amount_paise=amount_paise,
            description=description,
            event_id=event_id,
            fundraiser_id=fundraiser_id,
            task_id=task_id,
        )

    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"id": exp_id, "status": "SUBMITTED"}, status_code=201)

    return RedirectResponse(url=f"/expenses", status_code=303)


@router.post("/expenses/{expense_id}/receipt")
async def post_upload_receipt(
    request: Request,
    expense_id: int,
    session: Annotated[Session, Depends(get_current_session)],
    file: UploadFile = File(...),
    csrf_token: Annotated[str | None, Form()] = None,
) -> Response:
    """Handle POST /expenses/{expense_id}/receipt. Post upload receipt."""
    verify_csrf_token(session.csrf_token, csrf_token)
    content = await file.read(5 * 1024 * 1024 + 1)
    content_type = file.content_type or "application/octet-stream"

    with unit_of_work(get_db_path()) as conn:
        r_id = expense_service.attach_receipt(
            conn,
            expense_id=expense_id,
            uploader_id=session.user_id,
            file_content=content,
            original_filename=file.filename or "receipt.dat",
            mime_type=content_type,
        )

    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"id": r_id, "expense_id": expense_id}, status_code=201)
    return RedirectResponse("/expenses?notice=Receipt+attached", status_code=303)


@router.get("/receipts/{receipt_id}")
def download_receipt(
    request: Request,
    receipt_id: int,
    session: Annotated[Session, Depends(get_current_session)],
) -> Response:
    """Handle GET /receipts/{receipt_id}. Download receipt."""
    with unit_of_work(get_db_path()) as conn:
        cur = conn.execute(
            "SELECT uploader_id, stored_name, original_name, mime FROM receipts WHERE id = ?",
            (receipt_id,),
        )
        row = cur.fetchone()
        if not row:
            raise DomainError("NOT_FOUND", 404, "Receipt not found")

        uploader_id, stored_name, original_name, mime = row
        perms = get_user_permissions(conn, session.user_id)
        if session.user_id != uploader_id and "receipts.view_all" not in perms:
            raise DomainError("NOT_FOUND", 404, "Receipt not found")

        if getattr(conn, "dialect", None) == "postgres":
            from urllib.parse import quote

            content = conn.execute(
                "SELECT content FROM receipt_content WHERE stored_name=?",
                (stored_name,),
            ).fetchone()
            if not content:
                raise DomainError("NOT_FOUND", 404, "Receipt file not found")
            return Response(
                content=bytes(content[0]),
                media_type=mime,
                headers={
                    "X-Content-Type-Options": "nosniff",
                    "Content-Disposition": "attachment; filename*=UTF-8''"
                    + quote(original_name, safe=""),
                },
            )
    file_path = resolve_receipt_file(stored_name)
    return FileResponse(
        path=str(file_path),
        media_type=mime,
        filename=original_name,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post("/admin/expenses/{expense_id}/approve")
def post_approve_expense(
    request: Request,
    expense_id: int,
    session: Annotated[Session, Depends(require_perm("expenses.approve"))],
    csrf_token: Annotated[str, Form()],
    note: Annotated[str | None, Form()] = None,
) -> Response:
    """Handle POST /admin/expenses/{expense_id}/approve. Post approve expense."""
    verify_csrf_token(session.csrf_token, csrf_token)

    with unit_of_work(get_db_path()) as conn:
        j_id = expense_service.approve_expense(
            conn,
            expense_id=expense_id,
            approver_user_id=session.user_id,
            decision_note=note,
        )

    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse(
            {"expense_id": expense_id, "status": "APPROVED", "journal_entry_id": j_id}
        )
    return RedirectResponse("/expenses?notice=Expense+approved", status_code=303)


@router.post("/admin/expenses/{expense_id}/reject")
def post_reject_expense(
    request: Request,
    expense_id: int,
    session: Annotated[Session, Depends(require_perm("expenses.approve"))],
    csrf_token: Annotated[str, Form()],
    note: Annotated[str | None, Form()] = None,
) -> Response:
    """Handle POST /admin/expenses/{expense_id}/reject. Post reject expense."""
    verify_csrf_token(session.csrf_token, csrf_token)

    with unit_of_work(get_db_path()) as conn:
        expense_service.reject_expense(
            conn,
            expense_id=expense_id,
            approver_user_id=session.user_id,
            decision_note=note,
        )

    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"expense_id": expense_id, "status": "REJECTED"})
    return RedirectResponse("/expenses?notice=Expense+rejected", status_code=303)


@router.post("/admin/expenses/{expense_id}/pay")
def post_pay_expense(
    request: Request,
    expense_id: int,
    session: Annotated[Session, Depends(require_perm("expenses.pay"))],
    csrf_token: Annotated[str, Form()],
) -> Response:
    """Handle POST /admin/expenses/{expense_id}/pay. Post pay expense."""
    verify_csrf_token(session.csrf_token, csrf_token)

    with unit_of_work(get_db_path()) as conn:
        j_id = expense_service.pay_expense(
            conn,
            expense_id=expense_id,
            payer_user_id=session.user_id,
        )

    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse(
            {"expense_id": expense_id, "status": "PAID", "journal_entry_id": j_id}
        )
    return RedirectResponse("/expenses?notice=Reimbursement+recorded", status_code=303)
