"""Tasks and Fundraisers HTTP routes per CONTRACT.md §12.

Owner: C
Assigned branch: codex/treasury-comms

Routes:
  GET /fundraisers/{id}/board
  PATCH /tasks/{id}/status (auth, task owner or perm:tasks.manage)
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import JSONResponse

from clubledger.config import get_db_path
from clubledger.core.auth import get_current_session, get_user_permissions
from clubledger.core.csrf import verify_csrf_token
from clubledger.core.db import unit_of_work
from clubledger.core.types import Session
from clubledger.tasks import service as task_service

router = APIRouter(tags=["tasks"])


@router.get("/fundraisers/{fundraiser_id}/board")
def get_board(
    request: Request,
    fundraiser_id: int,
) -> Response:
    with unit_of_work(get_db_path()) as conn:
        board = task_service.get_fundraiser_board(conn, fundraiser_id)
    return JSONResponse(board)


@router.patch("/tasks/{task_id}/status")
def patch_task_status(
    request: Request,
    task_id: int,
    session: Annotated[Session, Depends(get_current_session)],
    status: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
) -> Response:
    verify_csrf_token(session.csrf_token, csrf_token)

    with unit_of_work(get_db_path()) as conn:
        perms = get_user_permissions(conn, session.user_id)
        is_staff = "tasks.manage" in perms or "admin" in perms
        task_service.update_task_status(
            conn,
            task_id=task_id,
            status=status,
            actor_user_id=session.user_id,
            is_staff=is_staff,
        )

    return JSONResponse({"task_id": task_id, "status": status})
