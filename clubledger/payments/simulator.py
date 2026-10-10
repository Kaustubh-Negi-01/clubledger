"""Local payment simulator signing and dispatch per CONTRACT.md §5."""

from datetime import datetime, timezone
import hashlib
import hmac
import json
import secrets
import sqlite3
from typing import Any, Literal

from clubledger.core import clock
from clubledger.core.types import EventOutcome, Handlers, Payment
from clubledger.payments.service import handle_event


def create_simulator_payload(
    payment: Payment, outcome: Literal["success", "fail"]
) -> dict[str, Any]:
    """Build simulator event payload per CONTRACT §5."""
    event_id = f"evt_{secrets.token_hex(16)}"
    event_type = "payment.succeeded" if outcome == "success" else "payment.failed"

    return {
        "event_id": event_id,
        "type": event_type,
        "payment_id": payment.public_id,
        "user_id": payment.user_id,
        "amount_paise": payment.amount_paise,
        "currency": "INR",
    }


def sign_simulator_payload(
    payload: dict[str, Any], secret: str, timestamp: int | None = None
) -> tuple[bytes, str]:
    """Sign simulator payload server-side. Returns (raw_body_bytes, signature_header)."""
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    if timestamp is None:
        now_iso = clock.now()
        now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00")).astimezone(timezone.utc)
        timestamp = int(now_dt.timestamp())

    sig = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.".encode("utf-8") + raw_body,
        hashlib.sha256,
    ).hexdigest()

    header = f"t={timestamp},v1={sig}"
    return raw_body, header


def dispatch_simulated_outcome(
    conn: sqlite3.Connection,
    handlers: Handlers,
    payment: Payment,
    outcome: Literal["success", "fail"],
    secret: str,
    journal: Any = None,
) -> EventOutcome:
    """Build, server-side sign, and process a simulated payment outcome."""
    payload = create_simulator_payload(payment, outcome)
    now = clock.now()
    raw_body, sig_header = sign_simulator_payload(payload, secret)

    return handle_event(
        conn,
        handlers=handlers,
        raw_body=raw_body,
        signature_header=sig_header,
        now=now,
        journal=journal,
    )
