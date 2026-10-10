"""Real email transport and retry-safe outbox worker.

Network calls happen outside database transactions. SENT means the provider
accepted the email, not proof that a recipient opened it or received it in inbox.
Local capture remains separate and cannot silently stand in for production mail.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import os
import re
import time
import uuid
import smtplib
import ssl
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from clubledger.config import get_env
from clubledger.core import clock
from clubledger.core.db import unit_of_work


class MailConfigurationError(Exception):
    """Missing server configuration; queued messages must remain queued."""


class DeliveryError(Exception):
    """Sanitized transport error; never persist response bodies or credentials."""

    def __init__(self, code, permanent=False):
        self.code = code
        self.permanent = permanent
        super().__init__(code)


@dataclass(frozen=True)
class Settings:
    key: str
    sender: str
    site: str
    provider: str = "resend"
    smtp_login: str = ""

    @classmethod
    def load(cls):
        provider = os.environ.get("CLUBLEDGER_MAIL_MODE")
        if provider not in {"resend", "brevo", "brevo_smtp"}:
            raise MailConfigurationError("Real email delivery is not enabled.")
        key_name = {
            "resend": "RESEND_API_KEY",
            "brevo": "BREVO_API_KEY",
            "brevo_smtp": "BREVO_SMTP_KEY",
        }[provider]
        key = os.environ.get(key_name, "")
        smtp_login = (
            os.environ.get("BREVO_SMTP_LOGIN", "") if provider == "brevo_smtp" else ""
        )
        sender = os.environ.get("CLUBLEDGER_MAIL_FROM", "")
        site = os.environ.get("CLUBLEDGER_SITE_URL", "").rstrip("/")
        url = urlsplit(site)
        if (
            not key
            or (provider == "brevo_smtp" and not smtp_login)
            or not re.fullmatch(r"[^\s<>@]+@[^\s<>@]+", sender)
            or "\n" in key
            or "\r" in key
            or url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.path
            or url.query
            or url.fragment
        ):
            raise MailConfigurationError(
                "Configure provider, verified sender and HTTPS site URL."
            )
        return cls(key, sender, site, provider, smtp_login)


def is_demo_address(email):
    """The seeded examples must never generate real deliveries."""
    domain = email.lower().rsplit("@", 1)[-1]
    return domain in {
        "skyline.edu",
        "example.com",
        "example.org",
        "example.net",
    } or domain.endswith((".example", ".test", ".invalid", ".localhost"))


def suppression_reason(conn, row):
    """Recheck preferences, user activity and current membership immediately before sending."""
    if is_demo_address(row["to_email"]):
        return "SYNTHETIC_ADDRESS"
    subscriber = conn.execute(
        "SELECT s.status,u.is_active FROM subscribers s LEFT JOIN users u ON u.id=s.user_id WHERE s.email=?",
        (row["to_email"],),
    ).fetchone()
    if subscriber and subscriber["status"] != "SUBSCRIBED":
        return "UNSUBSCRIBED"
    if subscriber and subscriber["is_active"] == 0:
        return "USER_INACTIVE"
    if row["kind"] == "ANNOUNCEMENT":
        return None if subscriber else "UNSUBSCRIBED"
    member = conn.execute(
        "SELECT m.*,u.is_active FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.id=?",
        (row["ref_id"],),
    ).fetchone()
    if not member or member["status"] not in ("ACTIVE", "EXPIRED"):
        return "MEMBERSHIP_REVOKED"
    if not member["is_active"]:
        return "USER_INACTIVE"
    if conn.execute(
        "SELECT 1 FROM memberships WHERE user_id=? AND id<>? AND status IN ('ACTIVE','PENDING') AND starts_at>=?",
        (member["user_id"], member["id"], member["expires_at"]),
    ).fetchone():
        return "MEMBERSHIP_RENEWED"
    remaining = (
        parse_time(member["expires_at"]) - parse_time(clock.now())
    ).total_seconds()
    if (
        (row["kind"] == "RENEW_30D" and not 7 * 86400 < remaining <= 30 * 86400)
        or (row["kind"] == "RENEW_7D" and not 0 < remaining <= 7 * 86400)
        or (row["kind"] == "EXPIRED" and remaining > 0)
    ):
        return "REMINDER_NO_LONGER_CURRENT"
    return None


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def send_resend(settings, row):
    """Fixed provider endpoint; stable payload and idempotency key across retries."""
    body = row["body"]
    body = body.replace(
        "Unsubscribe: /unsubscribe/", "Unsubscribe: " + settings.site + "/unsubscribe/"
    )
    body = body.replace(" at /join.", " at " + settings.site + "/join.")
    key = (
        "clubledger-"
        + hashlib.sha256((settings.site + ":" + row["dedupe_key"]).encode()).hexdigest()
    )
    headers = {
        "Authorization": "Bearer " + settings.key,
        "Content-Type": "application/json",
        "Idempotency-Key": key,
    }
    payload = {
        "from": settings.sender,
        "to": [row["to_email"]],
        "subject": row["subject"],
        "text": body,
    }
    request = Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=8) as response:
            data = json.loads(response.read(16384))
            if not data.get("id"):
                raise DeliveryError("INVALID_PROVIDER_RESPONSE")
            return data["id"]
    except HTTPError as error:
        # 409 or 429 can be transient; validation/auth failures need operator action.
        raise DeliveryError(
            "PROVIDER_HTTP_" + str(error.code),
            permanent=400 <= error.code < 500 and error.code not in {408, 409, 429},
        ) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise DeliveryError("PROVIDER_UNAVAILABLE") from None


def send_brevo(settings, row):
    """Send through a verified Brevo sender, including its no-domain fallback.

    Brevo owns any substituted sender domain; we never claim to own that domain.
    Its shorter deduplication window also requires a shorter retry cutoff.
    """
    body = (
        row["body"]
        .replace(
            "Unsubscribe: /unsubscribe/",
            "Unsubscribe: " + settings.site + "/unsubscribe/",
        )
        .replace(" at /join.", " at " + settings.site + "/join.")
    )
    identity = str(
        uuid.uuid5(uuid.NAMESPACE_URL, settings.site + ":" + row["dedupe_key"])
    )
    request = Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(
            {
                "sender": {"name": "ClubLedger", "email": settings.sender},
                "replyTo": {"name": "ClubLedger", "email": settings.sender},
                "to": [{"email": row["to_email"]}],
                "subject": row["subject"],
                "textContent": body,
                "headers": {"idempotencyKey": identity},
            }
        ).encode(),
        headers={
            "api-key": settings.key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=8) as response:
            data = json.loads(response.read(16384))
            if not data.get("messageId"):
                raise DeliveryError("INVALID_PROVIDER_RESPONSE")
            return data["messageId"]
    except HTTPError as error:
        # A duplicate response means the earlier attempt was already accepted.
        # Read only the machine code; never store a provider response or API key.
        if error.code == 400:
            try:
                if json.loads(error.read(16384)).get("code") == "duplicate_parameter":
                    return "PREVIOUSLY_ACCEPTED"
            except (ValueError, OSError):
                pass
        raise DeliveryError(
            "PROVIDER_HTTP_" + str(error.code),
            permanent=400 <= error.code < 500 and error.code not in {408, 429},
        ) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise DeliveryError("PROVIDER_UNAVAILABLE") from None


def send_brevo_smtp(settings, row):
    """Use Brevo's supported SMTP service with mandatory validated STARTTLS.

    SMTP has no idempotency API. An uncertain delivery must be reviewed, never
    automatically resent; the worker also refuses to reclaim a previous attempt.
    """
    message = EmailMessage()
    try:
        message["From"] = settings.sender
        message["To"] = row["to_email"]
        message["Reply-To"] = settings.sender
        message["Subject"] = row["subject"]
        identity = hashlib.sha256(
            (settings.site + ":" + row["dedupe_key"]).encode()
        ).hexdigest()
        message["Message-ID"] = (
            "<" + identity + "@" + urlsplit(settings.site).hostname + ">"
        )
        body = (
            row["body"]
            .replace(
                "Unsubscribe: /unsubscribe/",
                "Unsubscribe: " + settings.site + "/unsubscribe/",
            )
            .replace(" at /join.", " at " + settings.site + "/join.")
        )
        message.set_content(body)
        with smtplib.SMTP("smtp-relay.brevo.com", 587, timeout=8) as client:
            client.ehlo()
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
            client.login(settings.smtp_login, settings.key)
            refused = client.send_message(message)
            if refused:
                raise DeliveryError("RECIPIENT_REJECTED", permanent=True)
        return message["Message-ID"]
    except smtplib.SMTPAuthenticationError:
        raise DeliveryError("PROVIDER_AUTH_FAILED", permanent=True) from None
    except (smtplib.SMTPException, OSError, ValueError):
        raise DeliveryError("SMTP_REVIEW_REQUIRED", permanent=True) from None


def deliver_outbox(
    path=None, *, limit=30, announcement_id=None, transport=None, pace=True
):
    """Claim one message at a time, with five-minute leases and three bounded attempts.

    Uncertain attempts stop before the configured provider's idempotency window.
    FAILED messages require review rather than risking duplicate mail.
    """
    settings = Settings.load()  # Fail before changing any outbox record.
    transport = (
        transport
        or {"resend": send_resend, "brevo": send_brevo, "brevo_smtp": send_brevo_smtp}[
            settings.provider
        ]
    )
    if get_env() == "test" and transport in (send_resend, send_brevo, send_brevo_smtp):
        raise MailConfigurationError("Tests must use an injected transport.")
    if not 1 <= limit <= 30:
        raise ValueError("Mail batch limit must be between 1 and 30.")
    result = {"accepted": 0, "suppressed": 0, "failed": 0, "retrying": 0}
    batch_started = time.monotonic()
    for _ in range(limit):
        # Leave unclaimed messages queued for the next serverless invocation.
        if time.monotonic() - batch_started >= 25:
            break
        now = clock.now()
        lease_cutoff = (parse_time(now) - timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        with unit_of_work(path) as conn:
            row = conn.execute(
                "SELECT * FROM mail_outbox WHERE status='QUEUED' AND (attempts=0 OR processed_at<=?)"
                + (
                    " AND kind='ANNOUNCEMENT' AND ref_id=?"
                    if announcement_id is not None
                    else ""
                )
                + " ORDER BY id LIMIT 1",
                (lease_cutoff, announcement_id)
                if announcement_id is not None
                else (lease_cutoff,),
            ).fetchone()
            if not row:
                break
            row = dict(row)
            reason = suppression_reason(conn, row)
            if reason:
                conn.execute(
                    "UPDATE mail_outbox SET status='SUPPRESSED',suppressed_reason=?,processed_at=? WHERE id=?",
                    (reason, now, row["id"]),
                )
                result["suppressed"] += 1
                continue
            # first-attempt time persists in last_error while a claim/retry is queued.
            first = (
                row["last_error"].split("|", 1)[0]
                if row["attempts"] and row["last_error"]
                else now
            )
            try:
                age = (parse_time(now) - parse_time(first)).total_seconds()
            except ValueError:
                age = 24 * 3600  # An old/unknown attempt needs review, not a resend.
            # Brevo documents a 15-minute window for individual messages.
            # Stop at ten minutes; a delayed scheduler must not risk duplicates.
            retry_window = 10 * 60 if settings.provider == "brevo" else 23 * 3600
            if (
                row["attempts"] >= 3
                or age >= retry_window
                or (settings.provider == "brevo_smtp" and row["attempts"] > 0)
            ):
                conn.execute(
                    "UPDATE mail_outbox SET status='FAILED',last_error='REVIEW_REQUIRED',processed_at=? WHERE id=?",
                    (now, row["id"]),
                )
                result["failed"] += 1
                continue
            conn.execute(
                "UPDATE mail_outbox SET attempts=attempts+1,processed_at=?,last_error=? WHERE id=?",
                (now, first + "|IN_FLIGHT", row["id"]),
            )
        # No database writer lock is held during the external API request.
        try:
            transport(settings, row)
        except DeliveryError as error:
            status = (
                "FAILED" if error.permanent or row["attempts"] + 1 >= 3 else "QUEUED"
            )
            with unit_of_work(path) as conn:
                conn.execute(
                    "UPDATE mail_outbox SET status=?,last_error=?,processed_at=? WHERE id=? AND status='QUEUED'",
                    (status, first + "|" + error.code, clock.now(), row["id"]),
                )
            result["failed" if status == "FAILED" else "retrying"] += 1
            # Stop this batch on rate limits/outages instead of exhausting other messages.
            break
        else:
            with unit_of_work(path) as conn:
                conn.execute(
                    "UPDATE mail_outbox SET status='SENT',last_error=NULL,processed_at=? WHERE id=? AND status='QUEUED'",
                    (clock.now(), row["id"]),
                )
            result["accepted"] += 1
        if pace:
            time.sleep(0.6)  # Respect provider throughput without holding a DB lock.
    return result


def deliver_announcement(announcement_id):
    """Optional post-publication dispatch; missing configuration preserves the queue."""
    try:
        deliver_outbox(announcement_id=announcement_id)
    except MailConfigurationError:
        pass
