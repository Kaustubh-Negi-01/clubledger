# Backend: rules, security and HTTP requests

The Python package is `clubledger`, stored inside this folder. Imports still look like `from clubledger.core.db import unit_of_work`; installation maps that package to `backend/clubledger/`.

Start with `clubledger/main.py`, then follow an API route into a service.

| Path | Responsibility |
| --- | --- |
| `clubledger/main.py` | Creates FastAPI, checks incoming requests, registers routes and serves frontend assets |
| `clubledger/api/` | HTTP entry points: read request inputs, enforce access, call services and return HTML/JSON/redirects |
| `clubledger/core/` | Shared database transactions, clock, pricing, IDs and types |
| `clubledger/security/` | Authentication, sessions, permissions, CSRF, rate limits and request middleware |
| `clubledger/notifications/` | Account notices and persistent read receipts |
| `clubledger/auth/` | Authentication package; its HTTP routes are in `api/auth.py` |
| `clubledger/payments/` | Payment state machine, refunds, settlement, simulator and webhook validation |
| `clubledger/membership/` | Membership activation, renewal and verification rules |
| `clubledger/events/` | Capacity holds, ticket issuance, cancellation and admission |
| `clubledger/store/` | Stock reservations, order fulfillment, pickup and cancellation |
| `clubledger/tasks/` | Fundraiser/task creation, state transitions and board calculations |
| `clubledger/expenses/` | Submission, approval, reimbursement and validated receipt storage |
| `clubledger/journal/` | Balanced accounting entries and reversals |
| `clubledger/reports/` | Financial summaries, event reports and integrity checks |
| `clubledger/comms/` | Announcements, subscriptions, reminder queue and local mail capture |
| `clubledger/close/` | Semester checks, immutable snapshots and officer handover |
| `clubledger/presentation/` | Builds shared page context and QR images; the actual HTML lives in frontend |
| `clubledger/config.py` | Reads environment settings; does not contain API routes |
| `clubledger/paths.py` | Finds installed frontend assets and migration resources |
| `clubledger/wiring.py` | Explicitly connects payment purposes to the correct domain handlers |
| `clubledger/seed.py` | Inserts roles, permissions and optional demo data |
| `clubledger/cli.py` | Commands such as migrate, seed, start and check-integrity |

## Route versus service

An **API route** answers “what should happen when this URL is requested?” A **service** answers “what are the club's rules for this operation?” Keeping these separate lets tests exercise rules without opening a browser.

Example: `api/store.py` receives a reservation form. `store/service.py` checks stock and pricing, creates an order and payment inside a transaction. The route then redirects to the checkout page.

API routes may return HTML as well as JSON. We use direct SQLite queries, not an ORM. FastAPI handles HTTP routing; Uvicorn runs the server; Jinja renders HTML.
