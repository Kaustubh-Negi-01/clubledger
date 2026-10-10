"""Unit tests for Tasks service and board (TSK-01..04)."""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from clubledger.core.db import apply_migrations, unit_of_work
from clubledger.core.errors import DomainError
from clubledger.core import clock
from clubledger.tasks import service as task_service


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    monkeypatch.setenv("CLUBLEDGER_ENV", "test")
    clock.set_now("2026-10-10T10:00:00Z")
    yield
    clock.reset()


@pytest.fixture
def task_db_path(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        path = tf.name

    monkeypatch.setenv("CLUBLEDGER_DB_PATH", path)

    with unit_of_work(path) as conn:
        apply_migrations(conn)

        conn.execute("INSERT INTO terms (id, label, starts_at, status, created_at) VALUES (1, '2026-T1', '2026-08-01T00:00:00Z', 'OPEN', '2026-08-01T00:00:00Z')")
        conn.execute("INSERT INTO users (id, email, name, password_hash, is_active, created_at) VALUES (1, 'alice@club.org', 'Alice', 'scrypt$h', 1, '2026-08-01T00:00:00Z'), (2, 'bob@club.org', 'Bob', 'scrypt$h', 1, '2026-08-01T00:00:00Z')")

    yield path

    try:
        Path(path).unlink()
    except OSError:
        pass


def test_task_crud_and_status_transitions(task_db_path):
    with unit_of_work(task_db_path) as conn:
        f_id = task_service.create_fundraiser(conn, term_id=1, title="Fest", goal_paise=100000)

        # Invalid user raises 422
        with pytest.raises(DomainError) as exc:
            task_service.create_task(conn, fundraiser_id=f_id, title="Decorate", owner_user_id=999)
        assert exc.value.code == "VALIDATION"

        # Create tasks
        t1 = task_service.create_task(conn, fundraiser_id=f_id, title="Decorate", owner_user_id=1, due_at="2026-10-09T10:00:00Z", status="TODO")
        t2 = task_service.create_task(conn, fundraiser_id=f_id, title="Lighting", owner_user_id=2, status="DOING")

        # Non-owner non-staff cannot update status (403)
        with pytest.raises(DomainError) as exc:
            task_service.update_task_status(conn, task_id=t1, status="DONE", actor_user_id=2, is_staff=False)
        assert exc.value.code == "FORBIDDEN"

        # Owner can update status (TSK-03)
        task_service.update_task_status(conn, task_id=t1, status="DONE", actor_user_id=1, is_staff=False)

        # Board view (TSK-02)
        board = task_service.get_fundraiser_board(conn, f_id)
        assert board["counts"]["DONE"] == 1
        assert board["counts"]["DOING"] == 1
        assert len(board["tasks"]) == 2
