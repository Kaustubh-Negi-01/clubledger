# Stack decision: Next.js, Supabase, Vercel

The original contract (`CONTRACT.md`, `REQUIREMENTS.md`, `BUILD_ORDER.md`) planned Python, FastAPI and SQLite. The team lead then asked for Supabase for the database, Vercel for hosting, Google sign-in, and a production-quality interface. That changes the stack, not the business rules.

## What changed

| Contract plan | This build |
|---|---|
| FastAPI + Jinja2/HTMX | Next.js (App Router, Server Actions) |
| SQLite + plain SQL migrations | Postgres on Supabase + plain SQL migrations in `supabase/migrations` |
| Server-side sessions and scrypt passwords | Supabase Auth (Google, email and password, magic link) |
| Python service layer with one outer transaction | `api_*` SQL functions: each call is one transaction |
| Signed webhook from a payment simulator | Server-side simulator inside the same transaction; a live gateway attaches at the same step |
| Local mail capture + CLI commands | `mail_outbox` / `mail_capture` tables, "Deliver" button, daily Vercel cron for housekeeping |

## What was kept (the rules that matter)

- Money is integer paise. Prices, capacity, stock and ownership are decided on the server.
- Account is not membership. Non-members pay public prices. Purchases require sign-in.
- Multi-seat holds: one ticket per seat, `UNIQUE (hold_id, seat_index)`, guarded hold consumption, capacity released exactly once.
- Late payments after expiry or failure become an `UNFULFILLED` obligation (account 2000) with a refund or complete-the-order path; they block term close.
- A repeated success notification for an already paid payment has no effect.
- Full refunds only, as exact ledger reversals; blocked after a ticket is used or an order is picked up.
- Posted journal entries balance and are immutable (triggers). Entries only go into the open term; corrections are adjusting entries.
- Cumulative balances carry across terms. Close takes a watermark inside one transaction; opening + movement = closing per account.
- Membership year is 1 Aug to 1 Aug IST, independent of financial terms.
- Mail is re-checked at send time, suppressions are recorded, capture is exactly once.
- Roles are read from the database on every call. Receipts are private and downloaded through an authorizing route.

## Intentionally different

- No signed-webhook plumbing in the simulator. There is no external caller to authenticate yet; the payment outcome runs through an authenticated, ownership-checked function.
- No rate limiter service. Supabase Auth rate-limits sign-ins; the in-process token buckets of the Python plan do not suit serverless.
- Settlement is a treasurer action ("pay out") instead of a T+1 command.
- The requirement IDs in `REQUIREMENTS.md` still describe the intended behaviour; SQL tests in `scripts/test-db.ts` and browser tests in `scripts/e2e.ts` cover the flows listed in the README. They do not claim one-to-one coverage of all 108 IDs.
