# In plain English: Publishes announcements, respects subscriptions and captures queued mail locally.
"""Transactional announcements, subscription preferences and exactly-once local mail."""

import re
import secrets
from datetime import datetime

from clubledger.core import clock
from clubledger.core.errors import DomainError


def subscribe(conn, email, user_id=None):
    """Record a validated email subscription without undoing a previous unsubscribe."""
    email = email.strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise DomainError("VALIDATION", 422, "Enter a valid email address.")
    existing = conn.execute(
        "SELECT * FROM subscribers WHERE email=?", (email,)
    ).fetchone()
    if existing:
        # A public request must not reactivate a previously unsubscribed address.
        return existing["id"]
    now = clock.now()
    return conn.execute(
        "INSERT INTO subscribers(email,user_id,status,unsub_token,subscribed_at,created_at) VALUES(?,?,'SUBSCRIBED',?,?,?)",
        (email, user_id, secrets.token_urlsafe(32), now, now),
    ).lastrowid


def unsubscribe(conn, token):
    """Mark the subscription identified by its token as unsubscribed."""
    row = conn.execute(
        "SELECT id FROM subscribers WHERE unsub_token=?", (token,)
    ).fetchone()
    if not row:
        raise DomainError("NOT_FOUND", 404, "Subscription not found.")
    conn.execute(
        "UPDATE subscribers SET status='UNSUBSCRIBED',unsubscribed_at=? WHERE id=?",
        (clock.now(), row["id"]),
    )


def create_announcement(conn, author_id, title, body):
    """Save an announcement draft belonging to its author and financial term."""
    if not title.strip() or not body.strip() or len(title) > 160 or len(body) > 20000:
        raise DomainError(
            "VALIDATION",
            422,
            "Provide a title and announcement text within the displayed limits.",
        )
    term = conn.execute("SELECT id FROM terms WHERE status='OPEN'").fetchone()
    if not term:
        raise DomainError("TERM_CLOSED", 409)
    return conn.execute(
        "INSERT INTO announcements(author_id,term_id,title,body,status,created_at) VALUES(?,?,?,?,'DRAFT',?)",
        (author_id, term["id"], title.strip(), body.strip(), clock.now()),
    ).lastrowid


def publish(conn, announcement_id):
    """Publish a draft and queue eligible subscriber messages with deduplication."""
    row = conn.execute(
        "SELECT * FROM announcements WHERE id=?", (announcement_id,)
    ).fetchone()
    if not row:
        raise DomainError("NOT_FOUND", 404)
    if row["status"] == "PUBLISHED":
        return
    now = clock.now()
    conn.execute(
        "UPDATE announcements SET status='PUBLISHED',published_at=? WHERE id=?",
        (now, announcement_id),
    )
    for subscriber in conn.execute(
        "SELECT email,unsub_token FROM subscribers WHERE status='SUBSCRIBED'"
    ):
        body = (
            row["body"] + "\n\nUnsubscribe: /unsubscribe/" + subscriber["unsub_token"]
        )
        conn.execute(
            "INSERT INTO mail_outbox(dedupe_key,to_email,subject,body,kind,ref_table,ref_id,status,created_at) VALUES(?,?,?,?,'ANNOUNCEMENT','announcements',?,'QUEUED',?) ON CONFLICT(dedupe_key) DO NOTHING",
            (
                f"announcement:{announcement_id}:{subscriber['email'].lower()}",
                subscriber["email"],
                row["title"],
                body,
                announcement_id,
                now,
            ),
        )


def send_reminders(conn, as_of=None):
    """Queue eligible membership renewal reminders once for each reminder identity."""
    now = as_of or clock.now()
    at = datetime.fromisoformat(now.replace("Z", "+00:00"))
    count = 0
    for row in conn.execute(
        "SELECT m.*,u.email FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.status IN ('ACTIVE','EXPIRED')"
    ):
        remaining = (
            datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00")) - at
        ).total_seconds()
        kind = (
            "EXPIRED"
            if remaining <= 0
            else (
                "RENEW_7D"
                if remaining <= 7 * 86400
                else "RENEW_30D"
                if remaining <= 30 * 86400
                else None
            )
        )
        if kind:
            result = conn.execute(
                "INSERT INTO mail_outbox(dedupe_key,to_email,subject,body,kind,ref_table,ref_id,status,created_at) VALUES(?,?,?,?,?,'memberships',?,'QUEUED',?) ON CONFLICT(dedupe_key) DO NOTHING",
                (
                    f"reminder:{kind}:{row['id']}",
                    row["email"],
                    "Your ClubLedger membership",
                    "Review your membership and renewal options at /join.",
                    kind,
                    row["id"],
                    now,
                ),
            )
            count += result.rowcount
    conn.execute(
        "UPDATE memberships SET status='EXPIRED' WHERE status='ACTIVE' AND expires_at<=?",
        (now,),
    )
    return count


def _capture(conn, row, now):
    conn.execute(
        "INSERT INTO mail_capture(outbox_id,to_email,subject,body,captured_at,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(outbox_id) DO NOTHING",
        (row["id"], row["to_email"], row["subject"], row["body"], now, now),
    )


def process_mail_outbox(conn, limit=100):
    """Recheck delivery eligibility, then capture or suppress queued messages locally."""
    processed = 0
    for row in conn.execute(
        "SELECT * FROM mail_outbox WHERE status='QUEUED' ORDER BY id LIMIT ?", (limit,)
    ).fetchall():
        now = clock.now()
        reason = None
        if row["kind"] == "ANNOUNCEMENT":
            subscriber = conn.execute(
                "SELECT s.status,u.is_active FROM subscribers s LEFT JOIN users u ON u.id=s.user_id WHERE s.email=?",
                (row["to_email"],),
            ).fetchone()
            if not subscriber or subscriber["status"] != "SUBSCRIBED":
                reason = "UNSUBSCRIBED"
            elif subscriber["is_active"] == 0:
                reason = "USER_INACTIVE"
        else:
            member = conn.execute(
                "SELECT m.*,u.is_active FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.id=?",
                (row["ref_id"],),
            ).fetchone()
            if not member or member["status"] not in ("ACTIVE", "EXPIRED"):
                reason = "MEMBERSHIP_REVOKED"
            elif not member["is_active"]:
                reason = "USER_INACTIVE"
            elif conn.execute(
                "SELECT 1 FROM memberships WHERE user_id=? AND id<>? AND status IN ('ACTIVE','PENDING') AND starts_at>=?",
                (member["user_id"], member["id"], member["expires_at"]),
            ).fetchone():
                reason = "MEMBERSHIP_RENEWED"
        if reason:
            conn.execute(
                "UPDATE mail_outbox SET status='SUPPRESSED',suppressed_reason=?,processed_at=? WHERE id=?",
                (reason, now, row["id"]),
            )
        else:
            try:
                _capture(conn, row, now)
                conn.execute(
                    "UPDATE mail_outbox SET status='SENT',attempts=attempts+1,processed_at=?,last_error=NULL WHERE id=?",
                    (now, row["id"]),
                )
            except Exception as error:
                attempts = row["attempts"] + 1
                conn.execute(
                    "UPDATE mail_outbox SET status=?,attempts=?,last_error=?,processed_at=? WHERE id=?",
                    (
                        "FAILED" if attempts >= 3 else "QUEUED",
                        attempts,
                        type(error).__name__,
                        now,
                        row["id"],
                    ),
                )
        processed += 1
    return processed
