# Security: start here

This folder contains actual protections used by the application, not placeholder
files for an evaluator. Folder names do not guarantee a security score.

| File | What it protects |
| --- | --- |
| `auth.py` | Scrypt password hashes, login sessions, expiry, account permissions |
| `csrf.py` | Forms: verifies that requests carry the correct session token |
| `ratelimit.py` | Login and other sensitive endpoints: limits repeated requests |
| `middleware.py` | Login-required pages, CSRF enforcement, upload bounds, browser headers |

Routes in `backend/clubledger/api/` call these controls. Database constraints and
transactions remain in `database/` and `backend/clubledger/core/`. Payment webhook
signatures remain beside payment handling in `backend/clubledger/payments/webhook.py`.
Ownership checks remain beside the domain operation that knows who owns a record.

No credentials are stored here. Private settings come from ignored environment
files locally and server-only environment variables in Vercel.
