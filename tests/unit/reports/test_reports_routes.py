"""Unit tests for finance reports routes (CONTRACT §12).

Tests:
  - GET /finance (HTML and JSON)
  - GET /finance/accounts/{code}
  - GET /finance/entries/{id}
  - GET /finance/integrity
  - Access control: perm:finance.view required (401 without auth, 403 without permission).
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from clubledger.config import get_db_path
from clubledger.core.types import Line, Payment
from clubledger.core.db import apply_migrations, unit_of_work
from clubledger.core.auth import create_session
from clubledger.core import clock
from clubledger.journal import service as journal_service
from clubledger.reports.routes import router as finance_router


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    monkeypatch.setenv("CLUBLEDGER_ENV", "test")
    clock.set_now("2026-10-10T10:00:00Z")
    yield
    clock.reset()


@pytest.fixture
def app_and_db(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        path = tf.name

    monkeypatch.setenv("CLUBLEDGER_DB_PATH", path)

    with unit_of_work(path) as conn:
        apply_migrations(conn, files=["0001_core.sql", "0002_payments.sql", "0006_journal.sql"])

        # Seed roles, permissions, terms, users
        conn.execute(
            """
            INSERT INTO roles (id, code, created_at)
            VALUES (1, 'admin', '2026-08-01T00:00:00Z'),
                   (2, 'member', '2026-08-01T00:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO permissions (id, code, created_at)
            VALUES (1, 'finance.view', '2026-08-01T00:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO role_permissions (role_id, permission_id, created_at)
            VALUES (1, 1, '2026-08-01T00:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO users (id, email, name, password_hash, is_active, created_at)
            VALUES (1, 'admin@club.org', 'Admin User', 'scrypt$hash', 1, '2026-08-01T00:00:00Z'),
                   (2, 'member@club.org', 'Plain Member', 'scrypt$hash', 1, '2026-08-01T00:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO user_roles (id, user_id, role_id, granted_at, created_at)
            VALUES (1, 1, 1, '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z'),
                   (2, 2, 2, '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO terms (id, label, starts_at, status, created_at)
            VALUES (1, '2026-T1', '2026-08-01T00:00:00Z', 'OPEN', '2026-08-01T00:00:00Z')
            """
        )

        # Seed payment and journal entry
        conn.execute(
            """
            INSERT INTO payments (id, public_id, user_id, purpose, ref_table, ref_id, amount_paise, status, fulfillment, term_id, created_at)
            VALUES (101, 'pay_101', 1, 'DUES', 'memberships', 1, 50000, 'SUCCEEDED', 'FULFILLED', 1, '2026-10-10T10:00:00Z')
            """
        )
        p = Payment(101, "pay_101", 1, "DUES", "memberships", 1, 50000, "SUCCEEDED", "FULFILLED", 1)
        journal_service.post_payment_received(conn, p, fulfilled=True)

        admin_raw_token, _ = create_session(conn, user_id=1)
        member_raw_token, _ = create_session(conn, user_id=2)

    from clubledger.main import create_app
    app = create_app()
    app.include_router(finance_router)
    client = TestClient(app)

    yield client, admin_raw_token, member_raw_token

    try:
        Path(path).unlink()
    except OSError:
        pass


def test_finance_endpoints_auth_protection(app_and_db):
    client, admin_token, member_token = app_and_db

    # 1. No session cookie -> 401
    resp = client.get("/finance")
    assert resp.status_code == 401

    # 2. Member without finance.view -> 403
    client.cookies.set("cl_session", member_token)
    resp = client.get("/finance")
    assert resp.status_code == 403

    # 3. Admin with finance.view -> 200
    client.cookies.set("cl_session", admin_token)
    resp = client.get("/finance")
    assert resp.status_code == 200
    assert "Cash on Hand (1000)" in resp.text


def test_finance_json_and_drilldown(app_and_db):
    client, admin_token, _ = app_and_db
    client.cookies.set("cl_session", admin_token)

    # 1. JSON response for /finance
    resp = client.get("/finance", headers={"Accept": "application/json"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["cash_summary"]["in_clearing"] == 50000
    assert data["cash_summary"]["cash_on_hand"] == 0

    # 2. Account drilldown
    resp = client.get("/finance/accounts/1100", headers={"Accept": "application/json"})
    assert resp.status_code == 200
    acc_data = resp.json()
    assert acc_data["total_paise"] == 50000
    assert len(acc_data["items"]) == 1

    entry_id = acc_data["items"][0]["entry_id"]

    # 3. Entry drilldown
    resp = client.get(f"/finance/entries/{entry_id}", headers={"Accept": "application/json"})
    assert resp.status_code == 200
    entry_data = resp.json()
    assert entry_data["items"][0]["entry_id"] == entry_id
    assert entry_data["items"][0]["source_exists"] is True

    # 4. Integrity page
    resp = client.get("/finance/integrity", headers={"Accept": "application/json"})
    assert resp.status_code == 200
    integ_data = resp.json()
    assert integ_data["passed"] is True
    assert integ_data["checks"]["debits_equal_credits"]["status"] == "PASS"
