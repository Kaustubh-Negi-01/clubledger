"""Build recent notices from real data; store only each user's read receipts.

No fabricated alerts, external requests or background notification service.
The feed contains at most 20 recent notices and is refreshed on page navigation.
"""

from datetime import datetime, timedelta

from clubledger.core import clock
from clubledger.core.errors import DomainError


def _date(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def recent_notifications(conn, user_id):
    """Return this account's outcomes, renewal notices and published club updates."""
    notices = []
    labels = {"DUES": "Membership", "TICKET": "Ticket", "MERCH": "Merchandise"}
    for payment in conn.execute(
        "SELECT * FROM payments WHERE user_id=? AND status IN ('SUCCEEDED','FAILED','REFUNDED','EXPIRED') ORDER BY id DESC LIMIT 10",
        (user_id,),
    ):
        status = payment["status"]
        label = labels[payment["purpose"]]
        link = {"DUES": "/join", "TICKET": "/me", "MERCH": "/me/orders"}[
            payment["purpose"]
        ]
        if status == "SUCCEEDED" and payment["fulfillment"] == "UNFULFILLED":
            title = label + " payment needs review"
            message = "Payment was received, but your purchase could not be completed. Club staff must review it."
        elif status == "SUCCEEDED" and payment["fulfillment"] != "FULFILLED":
            title = label + " payment received"
            message = "Payment was received. Purchase confirmation is still pending; check its current status."
        elif status == "SUCCEEDED":
            title = label + " payment successful"
            message = {
                "DUES": "Your membership payment completed. View your membership details.",
                "TICKET": "Your ticket payment completed. View your tickets in Overview.",
                "MERCH": "Your order is paid. View its current pickup status in My orders.",
            }[payment["purpose"]]
        elif status == "REFUNDED":
            title = label + " payment refunded"
            message = "The refund is recorded. Open the related page to see the updated status."
        elif status == "FAILED":
            title = label + " payment unsuccessful"
            message = "This payment attempt failed. It did not confirm your purchase or activate membership."
        else:
            title = label + " payment expired"
            message = "This payment expired. Start a new purchase if you still want to proceed."
        notices.append(
            dict(
                key=f"payment:{payment['id']}:{status}:{payment['fulfillment']}",
                title=title,
                message=message,
                href=link,
                created_at=payment["refunded_at"]
                or payment["succeeded_at"]
                or payment["created_at"],
            )
        )

    now = _date(clock.now())
    for member in conn.execute(
        "SELECT id,status,expires_at,created_at FROM memberships WHERE user_id=? AND status IN ('ACTIVE','EXPIRED') ORDER BY id DESC LIMIT 5",
        (user_id,),
    ):
        # A future renewal already covering the next year makes this notice stale.
        renewed = conn.execute(
            "SELECT 1 FROM memberships WHERE user_id=? AND id<>? AND status='ACTIVE' AND starts_at>=?",
            (user_id, member["id"], member["expires_at"]),
        ).fetchone()
        remaining = (_date(member["expires_at"]) - now).total_seconds()
        if renewed or remaining > 30 * 86400:
            continue
        expired = remaining <= 0
        window = "expired" if expired else "7d" if remaining <= 7 * 86400 else "30d"
        notices.append(
            dict(
                key=f"membership:{member['id']}:{window}",
                title="Membership expired"
                if expired
                else "Membership renewal is due soon",
                message="Your membership has expired. Open Membership to renew."
                if expired
                else "Your membership expires within "
                + ("7" if window == "7d" else "30")
                + " days. Open Membership to review renewal.",
                href="/join",
                created_at=(
                    _date(member["expires_at"])
                    - timedelta(days=0 if expired else 7 if window == "7d" else 30)
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        )

    for announcement in conn.execute(
        "SELECT id,title,published_at FROM announcements WHERE status='PUBLISHED' ORDER BY published_at DESC,id DESC LIMIT 10"
    ):
        notices.append(
            dict(
                key=f"announcement:{announcement['id']}",
                title="Club announcement: " + announcement["title"],
                message="A published club update is available. Open it to read the full announcement.",
                href=f"/announcements/{announcement['id']}",
                created_at=announcement["published_at"],
            )
        )
    notices.sort(
        key=lambda item: (
            item["created_at"],
            int(item["key"].split(":")[1]),
            item["key"],
        ),
        reverse=True,
    )
    notices = notices[:20]
    read_keys = {
        row["notification_key"]
        for row in conn.execute(
            "SELECT notification_key FROM notification_reads WHERE user_id=?",
            (user_id,),
        )
    }
    for notice in notices:
        notice["unread"] = notice["key"] not in read_keys
    return notices


def mark_read(conn, user_id, key=None):
    """Mark only currently visible notices belonging to this account as read."""
    notices = recent_notifications(conn, user_id)
    if key is not None:
        notices = [notice for notice in notices if notice["key"] == key]
        if not notices:
            raise DomainError(
                "NOT_FOUND", http_status=404, message="Notification not found."
            )
    for notice in notices:
        conn.execute(
            "INSERT INTO notification_reads(user_id,notification_key,read_at) VALUES(?,?,?) ON CONFLICT(user_id,notification_key) DO NOTHING",
            (user_id, notice["key"], clock.now()),
        )
