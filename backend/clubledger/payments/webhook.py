# In plain English: Checks the callback signature and payload before any database write.
"""Webhook parsing, verification, and rate-limiting per CONTRACT.md §4.4, §5, §13.3."""

from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import re
from typing import Any

from clubledger.core import clock
from clubledger.core.errors import DomainError
from clubledger.security.ratelimit import enforce_rate_limit

logger = logging.getLogger(__name__)

SIG_HEADER_REGEX = re.compile(r"^t=(\d+),v1=([0-9a-fA-F]+)$")


def parse_signature_header(header: str | None) -> tuple[int, str]:
    """Parse 'X-Signature: t=<unix>,v1=<hex>' header."""
    if not header:
        raise DomainError("BAD_SIGNATURE", 400, "Missing X-Signature header")

    match = SIG_HEADER_REGEX.match(header.strip())
    if not match:
        raise DomainError("BAD_SIGNATURE", 400, "Malformed X-Signature header format")

    t_val = int(match.group(1))
    v1_val = match.group(2).lower()
    return t_val, v1_val


def verify_webhook_request(
    raw_body: bytes,
    signature_header: str | None,
    client_ip: str,
    secret: str,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    """Untrusted phase of webhook processing per CONTRACT §5.

    Enforces:
    1. Rate limit (60/min per IP) before signature check.
    2. Header format (t=<unix>,v1=<hex>).
    3. Timestamp tolerance (|now - t| <= 300 s).
    4. Body size limit (<= 4096 bytes).
    5. Constant-time HMAC-SHA256 signature verification.
    6. JSON schema validation.

    Zero database writes on rejection. Returns parsed event dict.
    """
    # 1. Rate limit (60 per min per IP)
    try:
        enforce_rate_limit(f"webhook:{client_ip}", limit=60, window_seconds=60)
    except DomainError as err:
        logger.warning(f"Webhook rate limit exceeded for IP {client_ip}")
        raise err

    # 2. Parse signature header
    try:
        t_stamp, v1_sig = parse_signature_header(signature_header)
    except DomainError as err:
        logger.warning(
            f"Webhook header parse failed from IP {client_ip}: {err.message}"
        )
        raise err

    # 3. Timestamp tolerance (|now - t| <= 300 s)
    if now_epoch is None:
        now_iso = clock.now()
        now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
        now_epoch = now_dt.timestamp()

    if abs(now_epoch - t_stamp) > 300:
        logger.warning(
            f"Webhook stale timestamp {t_stamp} vs now {now_epoch} from IP {client_ip}"
        )
        raise DomainError(
            "BAD_SIGNATURE", 400, "Stale event timestamp outside 300s window"
        )

    # 4. Body size limit (<= 4 KB)
    if len(raw_body) > 4096:
        logger.warning(
            f"Webhook oversize body ({len(raw_body)} bytes) from IP {client_ip}"
        )
        raise DomainError("VALIDATION", 400, "Body size exceeds 4096 bytes limit")

    # 5. Constant-time HMAC verification
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        f"{t_stamp}.".encode("utf-8") + raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig.lower(), v1_sig.lower()):
        logger.warning(f"Webhook bad signature from IP {client_ip}")
        raise DomainError("BAD_SIGNATURE", 400, "Invalid webhook signature")

    # 6. JSON schema validation
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        logger.warning(f"Webhook invalid JSON from IP {client_ip}: {exc}")
        raise DomainError("VALIDATION", 400, "Invalid JSON payload")

    if not isinstance(payload, dict):
        raise DomainError("VALIDATION", 400, "Event payload must be a JSON object")

    event_id = payload.get("event_id")
    event_type = payload.get("type")
    payment_id = payload.get("payment_id")
    user_id = payload.get("user_id")
    amount_paise = payload.get("amount_paise")
    currency = payload.get("currency")

    if not event_id or not isinstance(event_id, str):
        raise DomainError("VALIDATION", 400, "Missing or invalid 'event_id'")
    if event_type not in {"payment.succeeded", "payment.failed"}:
        raise DomainError(
            "VALIDATION",
            400,
            "Invalid 'type': must be payment.succeeded or payment.failed",
        )
    if not payment_id or not isinstance(payment_id, str):
        raise DomainError("VALIDATION", 400, "Missing or invalid 'payment_id'")
    if not isinstance(user_id, int):
        raise DomainError("VALIDATION", 400, "Missing or invalid 'user_id'")
    if not isinstance(amount_paise, int) or amount_paise <= 0:
        raise DomainError("VALIDATION", 400, "Missing or invalid 'amount_paise'")
    if currency != "INR":
        raise DomainError("VALIDATION", 400, "Currency must be 'INR'")

    return payload
