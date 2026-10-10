"""Unit tests for payment simulator signing and dispatch per CONTRACT §5."""

from pathlib import Path
import sqlite3
import pytest

from clubledger.core.db import apply_migrations, connect
from clubledger.core.types import FulfillResult, Payment, PurposeHandler
from clubledger.payments.service import create_payment
from clubledger.payments.simulator import (
    create_simulator_payload,
    dispatch_simulated_outcome,
    sign_simulator_payload,
)


@pytest.fixture
def sim_db(tmp_path: Path):
    db_file = tmp_path / "sim_test.db"
    conn = connect(str(db_file))
    apply_migrations(conn)

    conn.execute(
        "INSERT INTO terms (id, label, starts_at, ends_at, status, created_at) "
        "VALUES (1, '2026-Fall', '2026-08-01T00:00:00Z', NULL, 'OPEN', '2026-08-01T00:00:00Z');"
    )
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
        "VALUES (1, 'alice@example.com', 'Alice', 'hash', 1, '2026-08-01T00:00:00Z');"
    )
    conn.commit()
    conn.close()
    return str(db_file)


def test_create_and_sign_simulator_payload():
    payment = Payment(
        id=1,
        public_id="pay_sim_123",
        user_id=1,
        purpose="DUES",
        ref_table="memberships",
        ref_id=10,
        amount_paise=25000,
        status="PENDING",
        fulfillment="NONE",
        term_id=1,
    )
    payload = create_simulator_payload(payment, outcome="success")
    assert payload["type"] == "payment.succeeded"
    assert payload["payment_id"] == "pay_sim_123"
    assert payload["amount_paise"] == 25000
    assert payload["currency"] == "INR"

    raw_body, header = sign_simulator_payload(
        payload, secret="sim_secret_key", timestamp=1700000000
    )
    assert header.startswith("t=1700000000,v1=")
    assert len(header.split("v1=")[1]) == 64


def test_dispatch_simulated_outcome(sim_db: str):
    conn = connect(sim_db)
    try:
        p = create_payment(
            conn,
            user_id=1,
            purpose="DUES",
            ref_table="memberships",
            ref_id=10,
            amount_paise=25000,
        )

        handlers = {
            "DUES": PurposeHandler(
                purpose="DUES",
                fulfill=lambda c, pay, manual, now: FulfillResult("FULFILLED"),
                check_refundable=lambda c, pay: None,
                apply_refund=lambda c, pay, now: None,
            )
        }

        outcome = dispatch_simulated_outcome(
            conn,
            handlers=handlers,
            payment=p,
            outcome="success",
            secret="test_sim_secret",
        )
        assert outcome.outcome == "APPLIED"
        assert outcome.payment_id == p.id

        row = conn.execute(
            "SELECT status, fulfillment FROM payments WHERE id = ?;", (p.id,)
        ).fetchone()
        assert row["status"] == "SUCCEEDED"
        assert row["fulfillment"] == "FULFILLED"
    finally:
        conn.close()
