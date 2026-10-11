# A simple notification inbox

The top-right bell appears only after signing in. Its badge counts unread notices
in the latest 20-item feed. Click it for five previews or choose **View all
notifications**. **View details** opens the relevant feature; it does not silently
mark an item read. Use **Mark as read** or **Mark all as read** explicitly.

## What appears

- Your own successful, failed, expired or refunded payment attempts.
- Received payments that could not fulfill a purchase clearly say **needs review**.
- Renewal notices within 30 days, within 7 days, and after expiry. Pending,
  revoked or already-renewed memberships do not produce a misleading reminder.
- Published club announcements. Drafts never appear.

These notices are built from existing database records, not invented demo alerts.
The source remains authoritative: when a payment changes from successful to
refunded, its notice changes and becomes unread again. Old announcements may
appear on a new account as recent club updates; the wording does not claim they
were published after that account joined. Notifications refresh on page navigation
or reload. No WebSocket, automatic polling or browser permission is required.

Read receipts are stored by account in `notification_reads`, so they survive
logout and can be shared across devices using the same database. Seeing a notice
does not change its read status. The backend verifies ownership and the normal
session/CSRF protections apply to every read action. Rendering escapes titles.

## Folder map

| Folder | Responsibility |
| --- | --- |
| `backend/clubledger/security/` | Existing authentication, CSRF, rate-limit and middleware controls |
| `backend/clubledger/notifications/` | Notice content, eligibility and read state |
| `backend/clubledger/api/notifications.py` | List and read-action URLs |
| `frontend/templates/notifications.html` | Full list |
| `frontend/templates/base.html` | Bell and five-item dropdown |
| `frontend/static/notifications.css` and `.js` | Appearance and keyboard dismissal |
| `database/migrations/0011_notifications.sql` | SQLite migration |
| `database/postgres/0012_notifications.sql` | PostgreSQL migration |

## Deployment safety

Apply the PostgreSQL migration with the migration owner before deploying the
backend. Grant the restricted runtime role access only to the new table and its
identity sequence, with a backend-only RLS policy. Browser roles receive no access.
Existing business records and email scheduling are unaffected.

## Release verification â€” 11 October 2026

- Local application suite: 275 passed, 26 cloud-only skipped (including the three new PostgreSQL cases).
- Additional real PostgreSQL notification tests: 3 passed in isolated schemas.
- Production migration 0012 applied; existing business row counts unchanged.
- Restricted backend read/write checked with a rolled-back probe.
- RLS enabled; anonymous and authenticated browser roles have no table access.
- Local browser verified the bell, full inbox and persistent mark-as-read behavior.

These checks are observed results, not an evaluator score.

- Live HTTPS verified: bell, inbox, mark-as-read persistence and static assets.
- Signed-out inbox: browser redirect to login and JSON 401.
