# Reviewer preparation: explain the code you are presenting

Use these as study notes, not as claims that AI-generated code was manually written. Be ready to open the corresponding file and explain the flow in your own words.

## A short introduction

“ClubLedger is a student association management app. The Python/FastAPI backend serves Jinja HTML pages. SQLite stores users, memberships, tickets, merchandise orders and a double-entry ledger. CSS and a small JavaScript file provide the interface. Payments and email are local simulations, and automated tests verify important state transitions and permissions.”

## Show the repository

Open `README.md`, then the four folder READMEs. Explain that frontend files display information, API routes receive HTTP requests, backend services enforce rules, and SQL migrations define the database. `.env` configures a local machine; it is not the place for API source code.

## Walkthrough: a merchandise purchase

1. `frontend/templates/store/detail.html` displays product options and a form. It includes a CSRF token and idempotency key.
2. `backend/clubledger/api/store.py` receives `POST /store/reserve`, checks the session and input, and calls the store service.
3. `backend/clubledger/store/service.py` calculates the eligible price and reserves only available stock. Available stock is physical minus reserved stock.
4. The service creates the order and payment in the transaction. The route redirects to `/pay/{public_id}`.
5. `backend/clubledger/api/payments.py` processes a requested simulator outcome through the signed simulator and real payment service.
6. `backend/clubledger/payments/service.py` records the financial outcome and uses explicitly registered handlers from `wiring.py` to fulfill the order.
7. `backend/clubledger/journal/service.py` posts balanced financial entries.
8. The browser is redirected to the owned payment page with `result=1`. `frontend/templates/payments/result.html` reads the saved status and fulfillment, and `static/app.js` opens the modal. Confetti appears only for a succeeded and fulfilled purchase.
9. An officer records pickup. Physical and reserved quantities are decremented together; pickup cannot happen twice.

## Questions you should be able to answer

**Why are the frontend and backend separate folders?** They have different jobs. HTML/CSS/JS define the display and browser interactions; Python validates actions and enforces club rules. This app still runs as one server.

**What is the database?** SQLite, a local relational database file. Its schema is built by ten numbered migrations. We have 35 application tables, not one large table.

**Why keep accounts and memberships separate?** A user can have an account without being an active member. Discounts depend on eligible membership status, not merely login.

**How do you prevent selling the final seat or item twice?** The services perform guarded state/quantity updates inside a single-writer transaction. A stale reservation cannot silently fulfill after capacity is consumed elsewhere. Tests exercise these cases.

**How do you prevent duplicate purchases or callbacks?** Idempotency keys are scoped to actor, action and request hash. Verified callback event identity and guarded state transitions prevent repeated fulfillment and duplicate journal effects.

**How do you know a payment actually succeeded?** The app reads the saved payment status and fulfillment after processing the verified simulator event. The popup does not trust an arbitrary success query parameter.

**What happens if money arrives after a hold expires?** It is recorded as an unfulfilled obligation for an officer to resolve. The app does not oversell or claim that a ticket/order was delivered.

**How are finances protected?** Journal entries have balanced debit and credit lines. Database triggers protect posted history; refunds use reversing entries. Reporting distinguishes cumulative cash from per-period income and expenses.

**How is a logged-in user protected?** Sessions have expiry and revocation, actions require CSRF validation, and permissions gate officer operations. Ownership checks prevent reading another user's payment or changing their order.

**Where are your API keys?** There are no external payment/email/AI keys in this version. Local configuration is in the ignored `.env`, and the simulator uses a signing secret. Do not confuse development AI subscriptions with runtime APIs.

**What is tested?** The suite tests services and full HTTP journeys, including membership activation, payments, capacity, refunds, stock, accounting, close and permissions. See the current test output for the exact result. Requirement evidence remains a separate, incomplete tracker.

**What is incomplete for production?** Real payment-provider and mail delivery integrations, full requirement certification, and production deployment review. Do not present simulated charges as bank transactions or claim an evaluator score we have not received.

## Team study areas

| Person | Suggested area to explain | Files to study |
| --- | --- | --- |
| Kaustubh | App startup, security and payment flow | `main.py`, `core/`, `api/payments.py`, `payments/`, `wiring.py` |
| Saksham | Memberships, tickets and merchandise | `membership/`, `events/`, `store/`, their API routes and migrations 0003–0005 |
| Hamza | Financial rules, expenses and operational workflows | `journal/`, `reports/`, `expenses/`, `tasks/`, `comms/`, `close/` |
| Santosh | UI flow, accessibility and verification | `frontend/`, `tests/e2e/`, requirement evidence checker |

This is a preparation division, not an assertion of manual authorship. Everyone should understand the architecture and demonstrate one complete journey.
