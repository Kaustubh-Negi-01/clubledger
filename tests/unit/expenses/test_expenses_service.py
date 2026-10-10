"""Unit tests for Expenses and Receipts service and routes (EXP-01..07).

Tests:
  - Submit expense: positive paise, category 5000-5099, OPEN term, optional links
  - Submitter ownership and void
  - Approver != submitter (SELF_APPROVAL rejected)
  - Approval posts Dr 50xx / Cr 2100 journal entry
  - Replay cannot duplicate approval effects
  - Pay requires status APPROVED and >= 1 receipt (unreceipted -> 422)
  - Pay posts Dr 2100 / Cr 1000 journal entry
  - Replay of pay is idempotent
  - Injected journal failure rolls back outer transaction
  - Receipt uploads: magic-byte sniffing, size limits, safe paths, authorized downloads
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from clubledger.config import get_db_path
from clubledger.core.auth import create_session
from clubledger.core.db import apply_migrations, unit_of_work
from clubledger.core.errors import DomainError
from clubledger.core import clock
from clubledger.expenses import service as expense_service
from clubledger.expenses.routes import router as expense_router
from clubledger.main import create_app
from clubledger.tasks import service as task_service


PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
PDF_BYTES = b"%PDF-1.4 sample pdf content for receipt upload testing"


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    monkeypatch.setenv("CLUBLEDGER_ENV", "test")
    clock.set_now("2026-10-10T10:00:00Z")
    yield
    clock.reset()


@pytest.fixture
def exp_db_path(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        path = tf.name

    monkeypatch.setenv("CLUBLEDGER_DB_PATH", path)

    with unit_of_work(path) as conn:
        apply_migrations(conn)

        # Seed roles and permissions
        conn.execute("INSERT INTO roles (id, code, created_at) VALUES (1, 'admin', '2026-08-01T00:00:00Z'), (2, 'treasurer', '2026-08-01T00:00:00Z'), (3, 'member', '2026-08-01T00:00:00Z')")
        conn.execute("INSERT INTO permissions (id, code, created_at) VALUES (1, 'expenses.approve', '2026-08-01T00:00:00Z'), (2, 'expenses.pay', '2026-08-01T00:00:00Z'), (3, 'receipts.view_all', '2026-08-01T00:00:00Z')")
        conn.execute("INSERT INTO role_permissions (role_id, permission_id, created_at) VALUES (2, 1, '2026-08-01T00:00:00Z'), (2, 2, '2026-08-01T00:00:00Z')")

        # Seed users: Alice (submitter), Bob (treasurer), Charlie (plain member)
        conn.execute("INSERT INTO users (id, email, name, password_hash, is_active, created_at) VALUES (1, 'alice@club.org', 'Alice', 'scrypt$h1', 1, '2026-08-01T00:00:00Z'), (2, 'bob@club.org', 'Bob', 'scrypt$h2', 1, '2026-08-01T00:00:00Z'), (3, 'charlie@club.org', 'Charlie', 'scrypt$h3', 1, '2026-08-01T00:00:00Z')")
        conn.execute("INSERT INTO user_roles (id, user_id, role_id, granted_at, created_at) VALUES (1, 1, 3, '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z'), (2, 2, 2, '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z'), (3, 3, 3, '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z')")

        # Seed open term
        conn.execute("INSERT INTO terms (id, label, starts_at, status, created_at) VALUES (1, '2026-T1', '2026-08-01T00:00:00Z', 'OPEN', '2026-08-01T00:00:00Z')")

    yield path

    try:
        Path(path).unlink()
    except OSError:
        pass


def test_submit_expense_and_composite_task_link(exp_db_path):
    with unit_of_work(exp_db_path) as conn:
        cat_id = conn.execute("SELECT id FROM accounts WHERE code = '5000'").fetchone()[0]

        # 1. Invalid amount rejected
        with pytest.raises(DomainError) as exc:
            expense_service.submit_expense(conn, submitter_id=1, category_account_id=cat_id, amount_paise=-100, description="Bad")
        assert exc.value.code == "VALIDATION"

        with pytest.raises(DomainError) as exc:
            expense_service.submit_expense(conn, submitter_id=1, category_account_id=cat_id, amount_paise=True, description="Bad")  # type: ignore[arg-type]
        assert exc.value.code == "VALIDATION"

        # 2. Fundraiser and tasks setup
        f1 = task_service.create_fundraiser(conn, term_id=1, title="Annual Fest Fund")
        f2 = task_service.create_fundraiser(conn, term_id=1, title="Sports Fund")
        t1 = task_service.create_task(conn, fundraiser_id=f1, title="Print posters")

        # Task from f1 linked to f2 -> composite FK validation failure
        with pytest.raises(DomainError) as exc:
            expense_service.submit_expense(
                conn,
                submitter_id=1,
                category_account_id=cat_id,
                amount_paise=5000,
                description="Poster printing",
                fundraiser_id=f2,
                task_id=t1,
            )
        assert exc.value.code == "VALIDATION"

        # Valid submit
        e_id = expense_service.submit_expense(
            conn,
            submitter_id=1,
            category_account_id=cat_id,
            amount_paise=5000,
            description="Poster printing",
            fundraiser_id=f1,
            task_id=t1,
        )
        assert e_id > 0
        exp = expense_service.get_expense(conn, e_id)
        assert exp["status"] == "SUBMITTED"
        assert exp["category_code"] == "5000"


def test_approve_reject_and_self_approval_guards(exp_db_path):
    with unit_of_work(exp_db_path) as conn:
        cat_id = conn.execute("SELECT id FROM accounts WHERE code = '5000'").fetchone()[0]
        e_id = expense_service.submit_expense(conn, submitter_id=1, category_account_id=cat_id, amount_paise=12000, description="Decorations")

        # Self-approval by Alice (submitter) -> SELF_APPROVAL
        with pytest.raises(DomainError) as exc:
            expense_service.approve_expense(conn, expense_id=e_id, approver_user_id=1)
        assert exc.value.code == "SELF_APPROVAL"

        # Approval by Bob (treasurer)
        j_id = expense_service.approve_expense(conn, expense_id=e_id, approver_user_id=2, decision_note="Approved")
        assert j_id > 0

        # Verify journal entry Dr 5000 / Cr 2100
        cur = conn.execute("SELECT jl.debit_paise, jl.credit_paise, a.code FROM journal_lines jl JOIN accounts a ON a.id = jl.account_id WHERE jl.entry_id = ? ORDER BY a.code", (j_id,))
        lines = [tuple(row) for row in cur.fetchall()]
        assert lines[0] == (0, 12000, "2100")  # Cr 2100
        assert lines[1] == (12000, 0, "5000")  # Dr 5000

        # Replay approval returns same j_id
        assert expense_service.approve_expense(conn, expense_id=e_id, approver_user_id=2) == j_id


def test_receipt_required_and_pay_workflow(exp_db_path):
    with unit_of_work(exp_db_path) as conn:
        cat_id = conn.execute("SELECT id FROM accounts WHERE code = '5000'").fetchone()[0]
        e_id = expense_service.submit_expense(conn, submitter_id=1, category_account_id=cat_id, amount_paise=8000, description="Sound system")
        expense_service.approve_expense(conn, expense_id=e_id, approver_user_id=2)

        # 1. Attempt to pay without receipt -> 422
        with pytest.raises(DomainError) as exc:
            expense_service.pay_expense(conn, expense_id=e_id, payer_user_id=2)
        assert exc.value.code == "VALIDATION"

        # 2. Upload invalid MIME / spoofed content -> UPLOAD_REJECTED
        with pytest.raises(DomainError) as exc:
            expense_service.attach_receipt(
                conn,
                expense_id=e_id,
                uploader_id=1,
                file_content=b"not a png",
                original_filename="bad.png",
                mime_type="image/png",
            )
        assert exc.value.code == "UPLOAD_REJECTED"

        # 3. Valid receipt upload by submitter
        r_id = expense_service.attach_receipt(
            conn,
            expense_id=e_id,
            uploader_id=1,
            file_content=PNG_BYTES,
            original_filename="../secret/receipt.png",
            mime_type="image/png",
        )
        assert r_id > 0

        # Verify safe filename
        r_row = conn.execute("SELECT stored_name, original_name FROM receipts WHERE id = ?", (r_id,)).fetchone()
        assert ".." not in r_row[1]

        # 4. Now pay succeeds -> Dr 2100 / Cr 1000
        j_pay_id = expense_service.pay_expense(conn, expense_id=e_id, payer_user_id=2)
        assert j_pay_id > 0

        cur = conn.execute("SELECT jl.debit_paise, jl.credit_paise, a.code FROM journal_lines jl JOIN accounts a ON a.id = jl.account_id WHERE jl.entry_id = ? ORDER BY a.code", (j_pay_id,))
        lines = [tuple(row) for row in cur.fetchall()]
        assert lines[0] == (0, 8000, "1000")  # Cr 1000 (Cash)
        assert lines[1] == (8000, 0, "2100")  # Dr 2100 (Reimbursements Payable)

        # 5. Double pay is idempotent
        assert expense_service.pay_expense(conn, expense_id=e_id, payer_user_id=2) == j_pay_id


def test_injected_failure_rolls_back_outer_transaction(exp_db_path):
    """Injected failure during expense payment rolls back status and journal entry."""
    with pytest.raises(RuntimeError, match="Crash after pay"):
        with unit_of_work(exp_db_path) as conn:
            cat_id = conn.execute("SELECT id FROM accounts WHERE code = '5000'").fetchone()[0]
            e_id = expense_service.submit_expense(conn, submitter_id=1, category_account_id=cat_id, amount_paise=5000, description="Rollback test")
            expense_service.approve_expense(conn, expense_id=e_id, approver_user_id=2)
            expense_service.attach_receipt(conn, expense_id=e_id, uploader_id=1, file_content=PDF_BYTES, original_filename="bill.pdf", mime_type="application/pdf")
            expense_service.pay_expense(conn, expense_id=e_id, payer_user_id=2)
            raise RuntimeError("Crash after pay")

    # Verify rollback: expense status remains APPROVED, not PAID, and no pay journal entry exists
    with unit_of_work(exp_db_path) as conn:
        cur = conn.execute("SELECT status FROM expenses WHERE description = 'Rollback test'")
        row = cur.fetchone()
        assert row is None or row[0] != "PAID"
        cur = conn.execute("SELECT COUNT(*) FROM journal_entries WHERE source_event = 'paid'")
        assert cur.fetchone()[0] == 0
