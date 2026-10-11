"""Unit tests for untrusted webhook verification and rejection rules per CONTRACT §5."""

from datetime import datetime, timezone
import hashlib
import hmac
import json
import pytest

from clubledger.core import clock
from clubledger.core.errors import DomainError
from clubledger.security.ratelimit import reset_rate_limits
from clubledger.payments.webhook import parse_signature_header, verify_webhook_request


@pytest.fixture(autouse=True)
def reset_state():
    clock.reset()
    reset_rate_limits()
    yield
    clock.reset()
    reset_rate_limits()


def test_parse_signature_header_valid():
    t, v1 = parse_signature_header("t=1700000000,v1=abcdef1234567890abcdef1234567890")
    assert t == 1700000000
    assert v1 == "abcdef1234567890abcdef1234567890"


def test_parse_signature_header_invalid():
    with pytest.raises(DomainError) as exc:
        parse_signature_header(None)
    assert exc.value.code == "BAD_SIGNATURE"
    assert exc.value.http_status == 400

    with pytest.raises(DomainError) as exc:
        parse_signature_header("invalid_header_format")
    assert exc.value.code == "BAD_SIGNATURE"
    assert exc.value.http_status == 400


def test_verify_webhook_stale_timestamp():
    secret = "test_secret_123"
    clock_iso = clock.now()
    clock_dt = datetime.fromisoformat(clock_iso.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )
    t_stale = int(clock_dt.timestamp()) - 301

    payload = {
        "event_id": "evt_1",
        "type": "payment.succeeded",
        "payment_id": "pay_1",
        "user_id": 1,
        "amount_paise": 1000,
        "currency": "INR",
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(
        secret.encode("utf-8"), f"{t_stale}.".encode("utf-8") + raw_body, hashlib.sha256
    ).hexdigest()
    header = f"t={t_stale},v1={sig}"

    with pytest.raises(DomainError) as exc:
        verify_webhook_request(raw_body, header, "127.0.0.1", secret)
    assert exc.value.code == "BAD_SIGNATURE"
    assert exc.value.http_status == 400


def test_verify_webhook_oversize_body():
    secret = "test_secret_123"
    clock_iso = clock.now()
    clock_dt = datetime.fromisoformat(clock_iso.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )
    t = int(clock_dt.timestamp())

    large_body = b"x" * 4097
    sig = hmac.new(
        secret.encode("utf-8"), f"{t}.".encode("utf-8") + large_body, hashlib.sha256
    ).hexdigest()
    header = f"t={t},v1={sig}"

    with pytest.raises(DomainError) as exc:
        verify_webhook_request(large_body, header, "127.0.0.1", secret)
    assert exc.value.code == "VALIDATION"
    assert exc.value.http_status == 400


def test_verify_webhook_bad_signature():
    secret = "test_secret_123"
    clock_iso = clock.now()
    clock_dt = datetime.fromisoformat(clock_iso.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )
    t = int(clock_dt.timestamp())

    payload = {
        "event_id": "evt_1",
        "type": "payment.succeeded",
        "payment_id": "pay_1",
        "user_id": 1,
        "amount_paise": 1000,
        "currency": "INR",
    }
    raw_body = json.dumps(payload).encode("utf-8")
    header = f"t={t},v1=bad_hex_signature_here_0000000000000000"

    with pytest.raises(DomainError) as exc:
        verify_webhook_request(raw_body, header, "127.0.0.1", secret)
    assert exc.value.code == "BAD_SIGNATURE"
    assert exc.value.http_status == 400


def test_verify_webhook_schema_validation():
    secret = "test_secret_123"
    clock_iso = clock.now()
    clock_dt = datetime.fromisoformat(clock_iso.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )
    t = int(clock_dt.timestamp())

    # Invalid currency
    payload = {
        "event_id": "evt_1",
        "type": "payment.succeeded",
        "payment_id": "pay_1",
        "user_id": 1,
        "amount_paise": 1000,
        "currency": "USD",  # Must be INR
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(
        secret.encode("utf-8"), f"{t}.".encode("utf-8") + raw_body, hashlib.sha256
    ).hexdigest()
    header = f"t={t},v1={sig}"

    with pytest.raises(DomainError) as exc:
        verify_webhook_request(raw_body, header, "127.0.0.1", secret)
    assert exc.value.code == "VALIDATION"
    assert exc.value.http_status == 400


def test_verify_webhook_rate_limiting():
    secret = "test_secret_123"
    clock_iso = clock.now()
    clock_dt = datetime.fromisoformat(clock_iso.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )
    t = int(clock_dt.timestamp())

    payload = {
        "event_id": "evt_1",
        "type": "payment.succeeded",
        "payment_id": "pay_1",
        "user_id": 1,
        "amount_paise": 1000,
        "currency": "INR",
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(
        secret.encode("utf-8"), f"{t}.".encode("utf-8") + raw_body, hashlib.sha256
    ).hexdigest()
    header = f"t={t},v1={sig}"

    client_ip = "192.168.1.50"
    for _ in range(60):
        verify_webhook_request(raw_body, header, client_ip, secret)

    # 61st request in the same window must raise 429 RATE_LIMITED
    with pytest.raises(DomainError) as exc:
        verify_webhook_request(raw_body, header, client_ip, secret)
    assert exc.value.code == "RATE_LIMITED"
    assert exc.value.http_status == 429


def test_verify_webhook_valid_success():
    secret = "test_secret_123"
    clock_iso = clock.now()
    clock_dt = datetime.fromisoformat(clock_iso.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )
    t = int(clock_dt.timestamp())

    payload = {
        "event_id": "evt_valid_123",
        "type": "payment.succeeded",
        "payment_id": "pay_abc",
        "user_id": 42,
        "amount_paise": 5000,
        "currency": "INR",
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(
        secret.encode("utf-8"), f"{t}.".encode("utf-8") + raw_body, hashlib.sha256
    ).hexdigest()
    header = f"t={t},v1={sig}"

    parsed = verify_webhook_request(raw_body, header, "127.0.0.1", secret)
    assert parsed["event_id"] == "evt_valid_123"
    assert parsed["amount_paise"] == 5000
    assert parsed["currency"] == "INR"
