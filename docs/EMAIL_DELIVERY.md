# Announcement emails and renewal reminders

## Production verification

On 11 October 2026, the account owner setup email authenticated through Brevo
SMTP and the provider log recorded **Delivered** to the verified sender inbox.
Production uses `brevo_smtp`; API transports remain optional alternatives.
The SMTP key and scheduler secret are server-only and outside Git.
The final local suite passed 268 tests, with 23 cloud-only tests skipped.

## What is implemented

Publishing an announcement saves it and queues one message per subscribed
address. In production, a background worker attempts the new announcement's
first batch. A protected scheduled endpoint queues due renewal reminders and
drains the email queue in batches of at most 30.

The reminder windows are 30 days, 7 days, and membership expiry. Each reminder
identity is queued once. Membership reminders include a renewal link and an
unsubscribe link. Opt-out, renewed memberships and inactive accounts are
checked again before sending.

The new **Email delivery** officer page at `/admin/mail` shows setup state,
queued, accepted, failed and suppressed messages. Only users with the existing
`comms.mail_viewer` permission can view it or manually process a batch.

**SENT / Accepted means the provider accepted the email. It is not an inbox,
open or read receipt.** This implementation does not process delivery webhooks.
Local mail capture does not count as real delivery and is forbidden in prod.

## Provider configuration

### No owned domain: Brevo demo route

Create a free Brevo account and verify a sender email you control, such as your
Gmail address. Brevo documents temporary replacement of free sender addresses
with its compliant sender domain. This is suitable for proving the hackathon
flow, subject to account approval and a successful real inbox test. It is not a
permanent substitute for an authenticated organization domain. The Free plan
currently allows 300 sends per day; delivery is never guaranteed.

Configure `CLUBLEDGER_MAIL_MODE=brevo`, `BREVO_API_KEY` as a server-only secret,
and `CLUBLEDGER_MAIL_FROM` as that verified email. Site URL and scheduler secret
are the same as below. The Resend key is not used in Brevo mode.

Brevo retries use a stable UUID in `headers.idempotencyKey`. Its individual
email documentation describes a 15-minute deduplication window, so this worker
stops uncertain retries after ten minutes. A delayed scheduler may mark a
message `REVIEW_REQUIRED` rather than risk a duplicate. Review such a message
in the provider logs before taking further action; do not blindly requeue it.

References: [Brevo sender-address replacement](https://help.brevo.com/hc/en-us/articles/14925263522578-Comply-with-Gmail-Yahoo-and-Microsoft-s-requirements-for-email-senders),
[Free plan limits](https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan),
[Individual-message idempotency](https://developers.brevo.com/changelog/2021/11/10).

### Supported SMTP alternative

Brevo also provides `smtp-relay.brevo.com:587`. This is a separate supported
service authenticated by an SMTP key, not an API key. Configure
`CLUBLEDGER_MAIL_MODE=brevo_smtp`, `BREVO_SMTP_LOGIN` from the SMTP dashboard,
and `BREVO_SMTP_KEY` as a sensitive server-only variable. Sender and site URL
settings remain the same. The code requires STARTTLS with certificate and
hostname validation before transmitting credentials or messages.

SMTP has no provider idempotency API. The application will not automatically
resend an uncertain SMTP outcome or a claimed message left by a crashed worker.
It marks that message for review instead. A stable Message-ID assists operator
investigation but does not guarantee recipient deduplication. Accepted status
still means relay acceptance, not confirmed inbox delivery.

### Owned domain: Resend configuration

The repository does not contain credentials and cannot create a verified sender
by itself. Create a Resend account, verify a sender domain, and make a sending
API key scoped to that domain. The provider's test sender may support an initial
test to the account owner's inbox; it cannot replace a verified sender for
sending club announcements to arbitrary subscribers.

Store these as server-only Vercel production environment variables:

| Name | Value |
| --- | --- |
| `CLUBLEDGER_MAIL_MODE` | `resend` |
| `RESEND_API_KEY` | Private provider API key |
| `CLUBLEDGER_MAIL_FROM` | Verified sender address, such as `club@your-domain.com` |
| `CLUBLEDGER_SITE_URL` | `https://clubledger-gold.vercel.app` |
| `CRON_SECRET` | At least 32 random characters |

Do not put keys in frontend files, commit them, or paste them into chat. Preview
deployments should not have sending credentials; this avoids unintended sends
from experiments. Redeploy after changing production environment variables.

## Scheduling

`vercel.json` schedules the protected endpoint daily at 00:30 UTC (06:00 IST).
Vercel Hobby scheduling can run within the hour rather than at an exact minute.
This daily job provides the renewal safety net.

`.github/workflows/mail.yml` provides queue draining/retries approximately every
15 minutes. GitHub schedules can be delayed. It is disabled by default. After
the sender is verified and an inbox test succeeds, store the same cron secret
as GitHub Actions secret `CLUBLEDGER_CRON_SECRET` and set repository variable
`CLUBLEDGER_MAIL_ENABLED=true`. The workflow calls only the fixed production
URL and holds no database or email-provider credential. Public repositories may
have inactive scheduled workflows disabled by GitHub; check scheduler health.

Both schedulers authenticate with `Authorization: Bearer <CRON_SECRET>`.
Without a correct secret the endpoint returns 401 without touching the database.
Without provider configuration it returns 503 and preserves queued messages.

## Sending safeguards and retries

- No database write lock is held during external requests.
- A transaction claims each message with a five-minute lease before sending.
- Resend requests use a stable idempotency key and absolute HTTPS links.
- Temporary transport failures stop the batch and can retry after the lease.
- Up to three attempts are allowed. Permanent provider errors fail immediately.
- An uncertain attempt older than 23 hours is marked for review instead of
  resending outside the provider's 24-hour idempotency window.
- Failed messages are not automatically reset. Review provider logs first.
- Synthetic `@skyline.edu`, `*.example`, `*.test`, `*.invalid`, `*.localhost` and
  example.com/net/org addresses are suppressed rather than sent externally.
- Error details are sanitized; API keys and provider response bodies are never
  written to the outbox or shown in the interface.

This uses the existing database tables. No schema migration, payment changes,
role changes or demo-data reset is required. Once real delivery is activated,
queued synthetic messages will become suppressed; that is an intentional state
transition, not data deletion.

## Files to explain to a reviewer

| File | Responsibility |
| --- | --- |
| `backend/clubledger/comms/service.py` | Announcements, preferences and reminder generation; local capture |
| `backend/clubledger/comms/delivery.py` | Provider settings, eligibility, stable request, claim and retry worker |
| `backend/clubledger/api/comms.py` | Authenticated cron and officer status/process routes |
| `frontend/templates/mail_status.html` | Email setup and queue status display |
| `vercel.json` | Daily production invocation |
| `.github/workflows/mail.yml` | Optional frequent queue drain and retry invocation |
| `tests/unit/test_email_delivery.py` | Fake-provider tests exercising real database transactions |

Tests never send real emails. Validate one real opted-in recipient and the
provider log before enabling scheduled sending. Domain verification, inbox
placement and provider quotas remain external service dependencies.

References: [Resend send-email API](https://resend.com/docs/api-reference/emails/send-email),
[Resend idempotency](https://resend.com/docs/dashboard/emails/idempotency-keys),
[Vercel cron limits](https://vercel.com/docs/cron-jobs/usage-and-pricing).
