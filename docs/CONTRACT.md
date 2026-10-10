# ClubLedger Implementation Contract

Single club (Skyline Student Association). Python 3.12, FastAPI, Jinja2 + HTMX, SQLite (stdlib `sqlite3`, no ORM), plain SQL migrations. Local-first, no paid APIs. Documentation only: nothing here is implemented yet.

## 0. Global rules

| # | Rule |
|---|------|
| G1 | Money is `INTEGER` paise. Currency is fixed `INR`. No floats anywhere in money paths. Display formatting only in templates. |
| G2 | Prices, discounts, capacity, stock, and ownership are server-authoritative. Clients send IDs and quantities only, never amounts, prices, user IDs, or roles. |
| G3 | **Account ≠ membership.** A registered `users` row has no benefits. Benefits require an `ACTIVE` `memberships` row whose `[starts_on, expires_on)` covers "now". Non-members buy at public price. Every purchase requires login. |
| G4 | Timestamps are UTC ISO-8601 text (`YYYY-MM-DDTHH:MM:SSZ`). One clock function `core.clock.now()` is injectable for tests. |
| G5 | One connection per request. The route (or CLI command) owns the single outer transaction (`BEGIN IMMEDIATE` … `COMMIT`/`ROLLBACK`). Services take `conn` and **never** call `BEGIN`, `COMMIT`, or `ROLLBACK`. Nested transactions are forbidden. |
| G6 | SQLite pragmas on every connection: `foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`. |
| G7 | Every mutation is idempotent via a unique key (see §6). Replays return the original result and write nothing. |
| G8 | Errors are typed: `DomainError(code, http_status)`. Codes are listed in §9. |

## 1. Schema (migration files in BUILD_ORDER.md)

All tables `STRICT`. `id INTEGER PRIMARY KEY`. `created_at TEXT NOT NULL` on all tables (omitted below for brevity).

### 1.1 Core / auth (Owner A, `0001_core.sql`)

```
users(id, email TEXT UNIQUE NOT NULL COLLATE NOCASE, name TEXT NOT NULL,
      password_hash TEXT NOT NULL,            -- stdlib hashlib.scrypt, per-user salt
      is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)))
roles(id, code TEXT UNIQUE NOT NULL)          -- seeded: admin, treasurer, events, store, comms, door, verifier
permissions(id, code TEXT UNIQUE NOT NULL)    -- seeded, see §4.3
role_permissions(role_id FK, permission_id FK, PRIMARY KEY(role_id, permission_id))
user_roles(user_id FK, role_id FK, granted_at, revoked_at TEXT NULL,
           PRIMARY KEY(user_id, role_id, granted_at))
sessions(id, token_hash TEXT UNIQUE NOT NULL,  -- sha256 of random 32-byte token; raw token only in cookie
         user_id FK, csrf_token TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT NULL)
terms(id, label TEXT UNIQUE NOT NULL,          -- e.g. "2026-27"
      starts_on TEXT NOT NULL, ends_on TEXT NOT NULL,
      status TEXT NOT NULL CHECK(status IN ('OPEN','CLOSING','CLOSED')))
-- partial unique index: at most one OPEN/CLOSING term
CREATE UNIQUE INDEX ux_terms_one_open ON terms((1)) WHERE status IN ('OPEN','CLOSING');
audit_log(id, actor_user_id NULL, action TEXT, entity TEXT, entity_id INTEGER, detail TEXT)
idempotency_keys(key TEXT PRIMARY KEY, scope TEXT NOT NULL, result_ref TEXT NOT NULL)
```

Indexes: `sessions(user_id)`, `sessions(expires_at)`, `user_roles(user_id) WHERE revoked_at IS NULL`.

### 1.2 Payments (Owner A, `0002_payments.sql`)

```
payments(id, public_id TEXT UNIQUE NOT NULL,   -- opaque, used in simulator URLs
         user_id FK NOT NULL,
         purpose TEXT NOT NULL CHECK(purpose IN ('DUES','TICKET','MERCH')),
         ref_table TEXT NOT NULL, ref_id INTEGER NOT NULL,   -- membership / ticket order / merch order
         amount_paise INTEGER NOT NULL CHECK(amount_paise > 0),
         currency TEXT NOT NULL DEFAULT 'INR' CHECK(currency='INR'),
         status TEXT NOT NULL,                 -- §3.1
         fulfillment TEXT NOT NULL DEFAULT 'NONE',   -- §3.1
         settled_at TEXT NULL, refunded_at TEXT NULL,
         term_id FK NOT NULL)
UNIQUE(ref_table, ref_id) WHERE status NOT IN ('FAILED','EXPIRED')   -- one live payment per target
payment_events(id, event_id TEXT UNIQUE NOT NULL,   -- simulator-issued; idempotency key for webhook
               payment_id FK NULL, type TEXT NOT NULL, raw_body TEXT NOT NULL,
               signature_ok INTEGER NOT NULL, outcome TEXT NOT NULL)  -- APPLIED|IGNORED_DUP|REJECTED_*|MISMATCH
```

Indexes: `payments(user_id)`, `payments(status)`, `payments(ref_table, ref_id)`.

### 1.3 Membership (Owner B, `0003_membership.sql`)

```
membership_plans(id, code UNIQUE, name, dues_paise INTEGER NOT NULL CHECK(dues_paise>0),
                 ticket_discount_bps INTEGER NOT NULL CHECK(ticket_discount_bps BETWEEN 0 AND 10000),
                 merch_discount_bps  INTEGER NOT NULL CHECK(merch_discount_bps  BETWEEN 0 AND 10000),
                 is_active INTEGER NOT NULL DEFAULT 1)
memberships(id, user_id FK, plan_id FK, term_id FK,
            status TEXT NOT NULL CHECK(status IN ('PENDING','ACTIVE','EXPIRED','REVOKED')),
            starts_on TEXT NULL, expires_on TEXT NULL,
            member_code TEXT UNIQUE NULL,      -- short human code for manual check-in, set on activation
            qr_token TEXT UNIQUE NULL,         -- random; set on activation
            payment_id FK NULL, verified_by FK NULL, verified_at TEXT NULL)
-- one non-terminal membership per user per term
CREATE UNIQUE INDEX ux_member_user_term ON memberships(user_id, term_id) WHERE status IN ('PENDING','ACTIVE');
reminders(id, membership_id FK, kind TEXT CHECK(kind IN ('RENEW_30D','RENEW_7D','EXPIRED')),
          mail_id FK NULL, UNIQUE(membership_id, kind))
```

Annual expiry: `expires_on = term.ends_on` (exclusive end, midnight UTC). Default term = academic year.

### 1.4 Events & tickets (Owner B, `0004_events.sql`)

```
events(id, term_id FK, title, venue, starts_at, ends_at,
       capacity INTEGER NOT NULL CHECK(capacity>0),
       member_price_paise INTEGER NOT NULL CHECK(member_price_paise>=0),
       public_price_paise INTEGER NOT NULL CHECK(public_price_paise>=member_price_paise),
       status TEXT NOT NULL CHECK(status IN ('DRAFT','ON_SALE','CLOSED','CANCELLED')),
       max_per_order INTEGER NOT NULL DEFAULT 4)
ticket_holds(id, event_id FK, user_id FK, qty INTEGER CHECK(qty BETWEEN 1 AND 10),
             unit_price_paise INTEGER NOT NULL, price_tier TEXT CHECK(price_tier IN ('MEMBER','PUBLIC')),
             status TEXT NOT NULL CHECK(status IN ('HELD','CONSUMED','RELEASED','EXPIRED')),
             expires_at TEXT NOT NULL, released_at TEXT NULL)
tickets(id, event_id FK, hold_id FK UNIQUE, user_id FK, payment_id FK NULL,
        code TEXT UNIQUE NOT NULL,             -- opaque QR payload (random 16 bytes, base32)
        price_paise INTEGER NOT NULL, price_tier TEXT,
        status TEXT NOT NULL CHECK(status IN ('ISSUED','USED','REFUNDED','VOID')),
        used_at TEXT NULL, used_by FK NULL)
```

Capacity invariant: `sum(ticket_holds.qty WHERE status='HELD' AND expires_at>now) + count(tickets WHERE status IN ('ISSUED','USED')) <= events.capacity`, enforced inside the transaction (`BEGIN IMMEDIATE` serialises writers). One ticket row per seat (hold of qty 3 → 3 tickets, each with its own code).
Indexes: `ticket_holds(event_id,status)`, `ticket_holds(status,expires_at)`, `tickets(event_id,status)`, `tickets(user_id)`.

### 1.5 Store (Owner B, `0005_store.sql`)

```
products(id, name, description, base_price_paise INTEGER CHECK(>0), is_active)
variants(id, product_id FK, sku TEXT UNIQUE, size TEXT NOT NULL,
         on_hand INTEGER NOT NULL CHECK(on_hand>=0),
         UNIQUE(product_id,size))
merch_orders(id, user_id FK, term_id FK,
             status TEXT CHECK(status IN ('RESERVED','PAID','PICKED_UP','CANCELLED','EXPIRED','REFUNDED')),
             expires_at TEXT NOT NULL, total_paise INTEGER NOT NULL,
             price_tier TEXT, payment_id FK NULL, picked_up_at TEXT NULL, picked_up_by FK NULL)
merch_order_items(id, order_id FK, variant_id FK, qty INTEGER CHECK(qty BETWEEN 1 AND 10),
                  unit_price_paise INTEGER NOT NULL, UNIQUE(order_id, variant_id))
```

Stock model: `variants.on_hand` is physical stock decremented **at reservation** (RESERVED orders hold stock); restored on EXPIRED/CANCELLED/REFUNDED(pre-pickup). `available = on_hand`. No separate counter, so there is no drift.
Indexes: `merch_orders(user_id)`, `merch_orders(status,expires_at)`.

### 1.6 Journal (Owner C first, `0006_journal.sql`)

```
accounts(id, code TEXT UNIQUE, name, type TEXT CHECK(type IN ('ASSET','LIABILITY','INCOME','EXPENSE')))
journal_entries(id, term_id FK NOT NULL, entry_date TEXT NOT NULL,
                source_type TEXT NOT NULL, source_id INTEGER NOT NULL, source_event TEXT NOT NULL,
                memo TEXT, status TEXT NOT NULL CHECK(status IN ('DRAFT','POSTED')),
                posted_at TEXT NULL, reverses_entry_id FK NULL, adjusts_term_id FK NULL,
                UNIQUE(source_type, source_id, source_event))   -- idempotency for all effects
journal_lines(id, entry_id FK NOT NULL, account_id FK NOT NULL,
              debit_paise INTEGER NOT NULL DEFAULT 0 CHECK(debit_paise>=0),
              credit_paise INTEGER NOT NULL DEFAULT 0 CHECK(credit_paise>=0),
              CHECK((debit_paise=0) <> (credit_paise=0)))     -- exactly one side non-zero
-- triggers (the DB enforces immutability, not just code):
--  trg_lines_no_insert_posted : BEFORE INSERT ON journal_lines WHEN entry.status='POSTED' -> RAISE(ABORT)
--  trg_lines_no_update_posted / trg_lines_no_delete_posted : same
--  trg_entry_post_balanced    : BEFORE UPDATE OF status ON journal_entries WHEN NEW.status='POSTED'
--                               AND (sum(debit)<>sum(credit) OR count(lines)<2) -> RAISE(ABORT)
--  trg_entry_no_update_posted : BEFORE UPDATE/DELETE on POSTED entry (except none) -> RAISE(ABORT)
```

Indexes: `journal_lines(entry_id)`, `journal_lines(account_id)`, `journal_entries(term_id, entry_date)`, `journal_entries(source_type, source_id)`.

**Chart of accounts (seeded, fixed):**

| Code | Name | Type |
|------|------|------|
| 1000 | Cash on Hand/Bank | ASSET |
| 1100 | Payment Clearing (received, unsettled) | ASSET |
| 2000 | Unfulfilled Payments Obligation | LIABILITY |
| 2100 | Reimbursements Payable | LIABILITY |
| 4000 | Dues Income | INCOME |
| 4100 | Ticket Income | INCOME |
| 4200 | Merchandise Income | INCOME |
| 5000–5099 | Expense by category (5000 Events, 5010 Merch Stock, 5020 Fundraiser, 5090 Other) | EXPENSE |

### 1.7 Expenses, comms, tasks, close (Owner C)

`0007_expenses.sql`
```
receipts(id, uploader_id FK, expense_id FK NULL, stored_name TEXT UNIQUE NOT NULL,  -- random name outside static dir
         original_name TEXT, mime TEXT CHECK(mime IN ('image/png','image/jpeg','application/pdf')),
         size_bytes INTEGER CHECK(size_bytes BETWEEN 1 AND 5242880), sha256 TEXT NOT NULL)
expenses(id, submitter_id FK, term_id FK, category_account_id FK, amount_paise INTEGER CHECK(>0), description,
         event_id FK NULL, task_id FK NULL, fundraiser_id FK NULL,
         status TEXT CHECK(status IN ('SUBMITTED','APPROVED','REJECTED','PAID','VOID')),
         decided_by FK NULL, decided_at NULL, decision_note NULL, paid_by FK NULL, paid_at NULL)
```
`0008_comms.sql`
```
announcements(id, author_id FK, title, body, status CHECK(status IN ('DRAFT','PUBLISHED')), published_at NULL, term_id FK)
subscribers(id, email UNIQUE COLLATE NOCASE, user_id FK NULL, status CHECK(status IN ('SUBSCRIBED','UNSUBSCRIBED')),
            unsub_token TEXT UNIQUE NOT NULL, subscribed_at, unsubscribed_at NULL)
mail_outbox(id, to_email, subject, body, kind TEXT, ref_type NULL, ref_id NULL,
            status CHECK(status IN ('QUEUED','SENT','FAILED')), attempts INTEGER DEFAULT 0, last_error NULL, sent_at NULL,
            UNIQUE(kind, ref_type, ref_id, to_email))      -- idempotent enqueue
mail_capture(id, outbox_id FK, to_email, subject, body, captured_at)   -- the "local mail history"
```
`0009_tasks.sql`
```
fundraisers(id, term_id FK, title, goal_paise INTEGER NULL, status CHECK(status IN ('PLANNING','ACTIVE','DONE','CANCELLED')))
tasks(id, fundraiser_id FK, title, owner_user_id FK NULL, due_on TEXT NULL,
      status CHECK(status IN ('TODO','DOING','DONE','BLOCKED')))
```
`0010_close.sql`
```
close_snapshots(id, term_id FK UNIQUE, taken_at, taken_by FK, totals_json TEXT NOT NULL,
                content_sha256 TEXT NOT NULL)            -- immutable via triggers (no UPDATE/DELETE)
close_checks(id, term_id FK, code TEXT, passed INTEGER, detail TEXT, evaluated_at)
officer_handover(id, term_id FK UNIQUE, from_user_id FK, to_user_id FK, notes, completed_at,
                 role_changes_json TEXT)                 -- audit of what moved
```

## 2. Pricing and entitlement rules (shared, `core/pricing.py`, Owner A)

- `is_member(conn, user_id, at) -> Membership | None`: ACTIVE and `starts_on <= at < expires_on`.
- Price tier is decided **server-side at hold/reserve time** and frozen on the hold/order. Later membership changes do not reprice.
- Ticket unit price: `MEMBER` → `events.member_price_paise` (the event's explicit member price; the plan's `ticket_discount_bps` is applied to the public price and the **lower** of the two is used, so a plan can improve but never worsen the member price). `PUBLIC` → `public_price_paise`.
- Merch unit price: `base_price_paise * (10000 - merch_discount_bps) // 10000` (floor, integer arithmetic) for members, else base.
- Dues price: `membership_plans.dues_paise` at purchase time, frozen in `payments.amount_paise`.
- Free tickets (`price = 0`) skip payment: hold consumed directly via `fulfill_ticket_hold(payment=None)`; journal gets no entry.

## 3. State machines

### 3.1 Payment (`payments.status`) and fulfillment (`payments.fulfillment`)

`status` (money truth):

```
CREATED --simulator opens--> PENDING
PENDING --payment.succeeded (valid)--> SUCCEEDED
PENDING --payment.failed--> FAILED            (terminal; grants nothing)
CREATED/PENDING --expire command (>30 min)--> EXPIRED  (terminal; nothing received)
SUCCEEDED --refund(full)--> REFUNDED          (terminal)
any --event with wrong amount/currency/identity--> unchanged status; payment_events.outcome=MISMATCH; fulfillment untouched
```

`fulfillment` (what we owe in return):

```
NONE                  default; nothing received or nothing granted
FULFILLED             benefit granted (membership active / tickets issued / merch order PAID)
UNFULFILLED           money received but cannot grant: reservation EXPIRED/CANCELLED/over capacity/stock gone before success arrived,
                      or target already terminal. Booked to 2000 Unfulfilled Payments Obligation.
RESOLVED_REFUNDED     UNFULFILLED then refunded in full
RESOLVED_FULFILLED    UNFULFILLED then staff manually re-fulfilled (capacity/stock available) via /admin/payments/{id}/fulfill
```

Rules:
- **Mismatch** (amount≠`payments.amount_paise`, currency≠INR, `payment_public_id` unknown, or `user_id` in payload ≠ `payments.user_id`): record event with `outcome=MISMATCH`, mutate nothing, surface in `/admin/payments?problem=1`. No money is credited.
- **Pending/failed events** grant nothing and post no journal entry.
- **Late success** (valid success event, hold/order no longer `HELD`/`RESERVED`): `status=SUCCEEDED`, `fulfillment=UNFULFILLED`; journal `Dr 1100 / Cr 2000` for the amount. Obligation stays on the books until `RESOLVED_*`. Reports show it as a liability, never as income.
- **Duplicate event** (`payment_events.event_id` already seen): outcome `IGNORED_DUP`, no mutation, HTTP 200.
- Event ordering: **`FAILED` is terminal.** A later `payment.succeeded` for a `FAILED` payment is recorded as `MISMATCH` and flagged in `/admin/payments?problem=1` for manual review (no auto-credit, no journal entry).

### 3.2 Membership
`PENDING` (dues unpaid) → `ACTIVE` (on dues fulfillment) → `EXPIRED` (expiry command, `expires_on <= now`) | `REVOKED` (full refund or admin action). `PENDING` older than 24 h with `EXPIRED` payment is deleted by the hold-expiry command. Renewal creates a new `memberships` row in the next term (allowed ≥ 30 days before expiry).

### 3.3 Ticket hold / ticket
`HELD` → `CONSUMED` (payment fulfilled) | `RELEASED` (user cancel) | `EXPIRED` (expiry command, `expires_at<=now`, default TTL 10 min).
`ISSUED` → `USED` (check-in) | `REFUNDED` (full refund, only from `ISSUED`) | `VOID` (event cancelled, triggers refund).
Capacity release rule: hold consumption **converts** held seats into ticket seats; the capacity query counts `HELD` (unexpired) + `ISSUED/USED`, so converting a hold to tickets in the same transaction releases the held quantity **exactly once** (status flips `HELD→CONSUMED`, which removes it from the held term). `UPDATE ... SET status='CONSUMED' WHERE id=? AND status='HELD'` must affect exactly 1 row or the whole transaction rolls back.

### 3.4 Merch order
`RESERVED` (stock decremented, TTL 15 min) → `PAID` (fulfilled) → `PICKED_UP`; `RESERVED` → `EXPIRED`/`CANCELLED` (stock restored); `PAID` → `REFUNDED` (stock restored). `PICKED_UP` is terminal and cannot be refunded.

### 3.5 Expense
`SUBMITTED` → `APPROVED` | `REJECTED`; `APPROVED` → `PAID`; `SUBMITTED` → `VOID` (by submitter). Approver ≠ submitter (enforced). `PAID` terminal.

### 3.6 Announcement
`DRAFT` → `PUBLISHED` (enqueues one `mail_outbox` row per `SUBSCRIBED` subscriber; unique key makes it idempotent).

### 3.7 Term
`OPEN` → `CLOSING` (inside close transaction only) → `CLOSED`; creation of next `OPEN` term happens in the same transaction.

## 4. Auth, sessions, CSRF, permissions

### 4.1 Sessions
- Login: verify scrypt hash, create `sessions` row, cookie `cl_session=<raw token>` (`HttpOnly`, `SameSite=Lax`, `Secure` when not on localhost, `Path=/`). Absolute TTL 8 h, sliding idle TTL 2 h (`expires_at` refreshed at most once per minute).
- Logout sets `revoked_at`; any request with a revoked/expired session gets 401 and the cookie is cleared.
- **Authorization is re-read from the DB on every request** (`user_roles.revoked_at IS NULL` joined through `role_permissions`). No permissions are cached in the cookie or in process memory, so role revocation is immediate.
- Deactivating a user (`is_active=0`) revokes all their sessions in the same transaction.

### 4.2 CSRF
- Per-session `csrf_token`. Every browser `POST/PUT/PATCH/DELETE` must send it as form field `csrf_token` or header `X-CSRF-Token` (HTMX: set once in `hx-headers` on `<body>`). Constant-time compare. Missing/invalid → 403 `CSRF_FAILED`.
- **Exemption (documented, single route):** `POST /webhooks/payments` is exempt from CSRF because it has no cookie session; it is authenticated solely by the HMAC signature in §5. No other route is exempt.
- Unauthenticated state-changing routes (`/auth/register`, `/auth/login`, `/subscribe`) use a pre-session double-submit CSRF cookie `cl_csrf`.
- Ownership: every resource route loads by `id AND user_id = :current_user` (or requires the staff permission). Foreign IDs return 404, not 403.

### 4.3 Permissions (seeded `permissions.code`)
`members.verify`, `members.manage`, `events.manage`, `events.checkin`, `store.manage`, `store.fulfill`, `comms.publish`, `comms.mail_viewer`, `tasks.manage`, `expenses.approve`, `expenses.pay`, `receipts.view_all`, `finance.view`, `close.run`, `handover.run`, `payments.admin`, `users.manage`.

| Role | Permissions |
|------|-------------|
| admin | all |
| treasurer | `finance.view`, `expenses.approve`, `expenses.pay`, `receipts.view_all`, `payments.admin`, `close.run` |
| events | `events.manage`, `events.checkin`, `members.verify` |
| door | `events.checkin`, `members.verify` |
| verifier | `members.verify` |
| store | `store.manage`, `store.fulfill` |
| comms | `comms.publish`, `comms.mail_viewer`, `tasks.manage` |

Members (plain users) have no staff permissions. `comms.mail_viewer` and `receipts.view_all` must be granted explicitly (no implicit inheritance, including for `events`). Admin has them through "all". Receipt owner can always view their own receipt.

## 5. Payment simulator and webhook

Local simulator, no network. `payments/simulator.py`:
- `POST /pay/{public_id}/outcome` (browser, session + CSRF + ownership): fields `outcome ∈ {success, fail}`. The server builds the event body and **signs it server-side**: `sig = HMAC_SHA256(SIM_SECRET, f"{timestamp}.{raw_body}")`, then internally calls the same `payments.webhook.handle_event(conn, raw_body, signature, timestamp)` used by the HTTP webhook. The browser never sees the secret or the signature.
- `POST /webhooks/payments` (external-shaped; used by tests and a documented `scripts/sim_webhook.py`). Headers: `X-Signature: t=<unix>,v1=<hex>`. Reject if `|now - t| > 300 s`.
- Event JSON: `{"event_id","type":"payment.succeeded|payment.failed","payment_id":"<public_id>","user_id":int,"amount_paise":int,"currency":"INR"}`.
- `SIM_SECRET` read from env `CLUBLEDGER_SIM_SECRET`; app refuses to start in non-dev mode if unset; dev default is generated into `data/.sim_secret` (gitignored).

`handle_event` validation order (**all before any mutation**): (1) signature + timestamp window, (2) JSON schema, (3) `event_id` dedupe, (4) event type ∈ allowed set, (5) payment exists, (6) `user_id` matches, (7) currency == INR, (8) amount == `amount_paise`. Failure at 1–2 → 400 and the row is recorded with `signature_ok=0`; 3 → 200 `IGNORED_DUP`; 4–8 → 200 `MISMATCH`/`REJECTED_*`, no state change.

## 6. Idempotency & uniqueness keys

| Effect | Key |
|--------|-----|
| Webhook event | `payment_events.event_id` UNIQUE |
| Payment received journal | `journal_entries(source_type='payment', source_id=<payment.id>, source_event='received')` |
| Settlement journal | `(…, 'settled')` |
| Refund journal | `(…, 'refunded')` |
| Reimbursement journal | `(source_type='expense', source_id, source_event='approved'|'paid')` |
| Fulfillment | state guards (`UPDATE … WHERE status='HELD'` rows==1); `payments.fulfillment` set once from `NONE` |
| Reminder / announcement mail | `mail_outbox` unique `(kind, ref_type, ref_id, to_email)` |
| Browser double-submit | Hidden `idempotency_key` form field (uuid) on purchase POSTs, stored in `idempotency_keys` |

`post_entry` uses `INSERT … ON CONFLICT DO NOTHING` on the unique key; a replay returns the existing `entry_id` and posts nothing.

## 7. Journal posting patterns

All entries `term_id` = the OPEN term at posting time (see §10 for post-close). Amounts equal `payments.amount_paise`.

| Event | Debit | Credit |
|-------|-------|--------|
| Payment succeeded + fulfilled (DUES/TICKET/MERCH) | 1100 Clearing | 4000 / 4100 / 4200 |
| Payment succeeded + unfulfilled | 1100 Clearing | 2000 Unfulfilled Obligation |
| Obligation later fulfilled manually | 2000 | 4000/4100/4200 |
| **Settlement** (`cli settle`, simulated T+1 payout, default: all SUCCEEDED unsettled payments older than 1 day; full payment amount, no fees) | 1000 Cash | 1100 Clearing |
| Full refund, not yet settled | income account (or 2000 if unfulfilled) | 1100 Clearing |
| Full refund, already settled | income account (or 2000) | 1000 Cash |
| Expense approved | 50xx category | 2100 Reimbursements Payable |
| Expense paid (reimbursement) | 2100 | 1000 Cash |

Refunds are **reversal entries** (`reverses_entry_id` set), never edits. Refund order: reverse income, then if the payment was settled credit cash, else credit clearing.

## 8. Refund rules (full refunds only)
`refund_payment(conn, payment_id, actor_id)`:
- Requires `payments.admin`. Payment must be `SUCCEEDED` and not `REFUNDED`.
- DUES: membership → `REVOKED`; discount entitlement ends immediately (the price resolver requires `ACTIVE`). Default: refund is always allowed; tickets/merch already bought at member price are not clawed back.
- TICKET: all tickets for the payment must be `ISSUED`; if any `USED` → reject `REFUND_BLOCKED`. Otherwise tickets → `REFUNDED`, capacity freed (they stop counting).
- MERCH: order must be `PAID`; `PICKED_UP` → reject `REFUND_BLOCKED`. Stock restored.
- `UNFULFILLED` payments refund with `fulfillment=RESOLVED_REFUNDED`, debiting 2000.
- Partial refunds do not exist; there is no amount parameter.

## 9. Error codes
`AUTH_REQUIRED(401)`, `FORBIDDEN(403)`, `CSRF_FAILED(403)`, `NOT_FOUND(404)`, `VALIDATION(422)`, `SOLD_OUT(409)`, `INSUFFICIENT_STOCK(409)`, `HOLD_EXPIRED(409)`, `ALREADY_MEMBER(409)`, `BAD_SIGNATURE(400)`, `STALE_EVENT(400)`, `REFUND_BLOCKED(409)`, `ALREADY_USED(409)`, `TERM_CLOSED(409)`, `CLOSE_BLOCKED(409)`, `SELF_APPROVAL(403)`, `UPLOAD_REJECTED(422)`, `RATE_LIMITED(429)`.

## 10. Semester close, snapshot, handover (Owner C)

`close.service.run_close(conn, term_id, actor_id) -> SnapshotId` runs inside the caller's single `BEGIN IMMEDIATE` transaction. **Atomic: the checks, snapshot, term transition, and new term either all commit or none do.**

Checklist (all must pass or `CLOSE_BLOCKED` with the failing `close_checks` rows returned; no partial writes):
1. No `payments` in `CREATED`/`PENDING`/`UNFULFILLED` (status `SUCCEEDED` + fulfillment `UNFULFILLED` must be resolved or refunded).
2. No expenses in `SUBMITTED`/`APPROVED` (must be `PAID`/`REJECTED`/`VOID`).
3. No live `HELD` ticket holds and no `RESERVED` merch orders.
4. All `journal_entries` for the term are `POSTED`; sum(debits)==sum(credits) per entry and for the term.
5. 2100 Reimbursements Payable balance == 0 and 2000 Obligation balance == 0.
6. Cash reconciliation: 1100 Clearing balance == 0 (all received payments settled) — `cli settle` first.
7. Every `PAID` expense above ₹0 has ≥1 receipt.

Then: compute `totals_json` (see §11 summary + per-source totals + event proceeds), `content_sha256 = sha256(canonical json)`, insert `close_snapshots` (triggers forbid UPDATE/DELETE), set term `CLOSED`, insert next `OPEN` term (starts the day after `ends_on`), expire all `ACTIVE` memberships whose `expires_on <= new term start` (they are not auto-renewed).

**After close:**
- Closed-term rows (journal, payments, expenses, events) are read-only. A trigger on `journal_entries` rejects insert where `term_id` is `CLOSED`, unless `adjusts_term_id` is set.
- New purchases made after close post into the new OPEN term. A payment *created* in the closed term but whose success arrives after close cannot exist (check 1 blocks close), so no cross-term payments occur.
- Corrections to closed periods are **adjusting entries** in the open term: `journal_entries.term_id = open`, `adjusts_term_id = closed`, `memo` required, requires `close.run`. Reports show them in the open term and list them under "Adjustments to prior terms". The snapshot is never modified.

Officer handover: `handover.service.run_handover(conn, term_id, from_user_id, to_user_id, role_codes, notes)`; precondition: term `CLOSED` and snapshot exists. In one transaction: revoke roles from `from_user` (set `revoked_at`), grant to `to_user`, revoke `from_user`'s sessions, write `officer_handover` with `role_changes_json`, audit-log. Requires `handover.run`. Admin role transfer requires at least one other active admin to remain (else `VALIDATION`).

## 11. Reports (Owner C, all queries over POSTED lines only, filtered by `term_id`)

- **Cash summary**: `cash_on_hand = balance(1000)`, `in_clearing = balance(1100)`, `obligations = balance(2000)`, `reimbursements_payable = balance(2100)`. Balance of asset = ΣDr−ΣCr; liability/income = ΣCr−ΣDr.
- **Income by source** (4000/4100/4200), **Expenses by category** (50xx), **Net = income − expenses**.
- **Drill-down**: total → account → journal entry → source document (payment, order, expense, ticket) with links; each level's sum equals the parent's.
- **Event report**: `proceeds = Σ ticket income for event net of refunds`; `attended = count(tickets USED)`; `sold = count(ISSUED+USED)`; `no_shows = sold − attended`. Event proceeds are computed from `payments` joined via `tickets.payment_id`, not from the journal alone, and a test asserts both agree.
- **Invariant check page** (`/finance/integrity`): Σ all posted debits == Σ credits; every SUCCEEDED payment has exactly one `received` entry; every `PAID` expense has `approved` and `paid` entries.

## 12. Endpoints and permissions

`auth` = logged-in session; `own` = ownership enforced; `perm:x` = permission x. All mutating browser routes: CSRF.

### Auth / account (A)
| Method Path | Access | Notes |
|---|---|---|
| GET/POST `/auth/register` | public | creates user only, no membership |
| GET/POST `/auth/login`, POST `/auth/logout` | public / auth | |
| GET `/me` | auth | account + membership status + tickets + orders |

### Membership (B)
| GET `/join` | auth | plan list, "become a member" |
| POST `/join` | auth, CSRF | creates `PENDING` membership + payment; redirect `/pay/{public_id}` |
| GET `/members/card` | auth, own | member code + QR |
| GET `/verify` (+ POST `/verify/lookup`) | perm:members.verify | by `member_code` or scanned `qr_token`; shows ACTIVE/EXPIRED + name only |
| GET `/admin/members` | perm:members.manage | list, expiring soon |

### Payments (A)
| GET `/pay/{public_id}` | auth, own | simulator page |
| POST `/pay/{public_id}/outcome` | auth, own, CSRF | server signs and dispatches |
| POST `/webhooks/payments` | signature only | **CSRF-exempt** |
| GET `/admin/payments` | perm:payments.admin | filters: problem, unfulfilled |
| POST `/admin/payments/{id}/refund`, `/fulfill` | perm:payments.admin, CSRF | |

### Events (B)
| GET `/events`, `/events/{id}` | public | shows member + public price, seats left |
| POST `/events/{id}/hold` | auth, CSRF | qty; creates hold + payment; redirect `/pay/…` |
| GET `/tickets/{id}` | auth, own | QR |
| GET/POST `/admin/events…` | perm:events.manage | create/edit/open/close/cancel |
| GET `/checkin/{event_id}`, POST `/checkin/{event_id}/scan` | perm:events.checkin | `code` (QR text or manual entry) |
| GET `/admin/events/{id}/report` | perm:events.manage or perm:finance.view | |

### Store (B)
| GET `/store`, `/store/{product_id}` | public | |
| POST `/store/reserve` | auth, CSRF | cart = list of `(variant_id, qty)`; all-or-nothing |
| POST `/store/orders/{id}/cancel` | auth, own, CSRF | |
| GET `/me/orders` | auth, own | |
| GET/POST `/admin/store…` | perm:store.manage | products, variants, stock adjust |
| POST `/admin/orders/{id}/pickup` | perm:store.fulfill, CSRF | |

### Comms / tasks (C)
| GET `/`, `/announcements`, `/announcements/{id}` | public | |
| POST `/subscribe`, GET/POST `/unsubscribe/{token}` | public (pre-session CSRF) | one-click via token |
| GET/POST `/admin/announcements…` | perm:comms.publish | create, publish |
| GET `/dev/mail`, `/dev/mail/{id}` | perm:comms.mail_viewer | captured mail history |
| GET/POST `/admin/fundraisers…`, `/admin/tasks…` | perm:tasks.manage | board view: per fundraiser, tasks by status, overdue count |
| PATCH `/tasks/{id}/status` | auth + (owner of task or perm:tasks.manage), CSRF | |

### Expenses / finance (C)
| GET/POST `/expenses/new`, GET `/expenses` | auth | members may submit; list own |
| POST `/expenses/{id}/receipt` | auth, own | upload ≤5 MB, mime allow-list, magic-byte sniff |
| GET `/receipts/{id}` | owner or perm:receipts.view_all | streamed; `Content-Disposition: attachment`, `nosniff`, never under `/static` |
| POST `/admin/expenses/{id}/approve|reject|pay` | perm:expenses.approve / expenses.pay | approver ≠ submitter |
| GET `/finance`, `/finance/accounts/{code}`, `/finance/entries/{id}`, `/finance/integrity` | perm:finance.view | |
| GET/POST `/admin/close` | perm:close.run | checklist view + run |
| GET/POST `/admin/handover` | perm:handover.run | |

## 13. Shared service signatures and transaction ownership

All in `clubledger/` package. **Services receive `conn: sqlite3.Connection` and never open/commit a transaction.** Routes and CLI commands use `with unit_of_work(db_path) as conn:` (`core/db.py`, Owner A) which issues `BEGIN IMMEDIATE`, commits on normal exit, rolls back on exception.

```python
# core/db.py (A)
def connect(path: str) -> sqlite3.Connection
@contextmanager
def unit_of_work(path: str) -> Iterator[sqlite3.Connection]

# core/auth.py (A)
def create_session(conn, user_id: int) -> tuple[str, str]            # (raw_token, csrf_token)
def load_session(conn, raw_token: str) -> Session | None             # also resolves live permissions
def revoke_session(conn, session_id: int) -> None
def require_perm(code: str) -> Depends                               # FastAPI dependency, reads DB each call
def verify_csrf(session, supplied: str) -> None

# core/pricing.py (A)
def active_membership(conn, user_id: int, at: str) -> Membership | None
def ticket_price(conn, event_id: int, user_id: int, at: str) -> tuple[int, Literal["MEMBER","PUBLIC"]]
def merch_price(conn, base_paise: int, user_id: int, at: str) -> tuple[int, Literal["MEMBER","PUBLIC"]]

# payments/service.py (A)
def create_payment(conn, *, user_id, purpose, ref_table, ref_id, amount_paise) -> Payment
def handle_event(conn, raw_body: bytes, signature_header: str, now: str) -> EventOutcome
def refund_payment(conn, payment_id: int, actor_id: int) -> None
def settle_payments(conn, as_of: str) -> int
# fulfillment dispatch: payments.service.fulfill(conn, payment) calls the registered handler for payment.purpose
FULFILLERS: dict[str, Callable[[sqlite3.Connection, Payment], FulfillResult]]  # populated at import by B's modules

# membership/service.py (B)
def start_join(conn, user_id, plan_id) -> Payment
def fulfill_dues(conn, payment) -> FulfillResult          # PENDING->ACTIVE, member_code, qr_token
def revoke_membership_for_refund(conn, payment) -> None
def lookup_member(conn, *, code=None, qr_token=None, at: str) -> MemberCheck
def send_renewal_reminders(conn, as_of: str) -> int       # enqueue only

# events/service.py (B)
def create_hold(conn, user_id, event_id, qty, idempotency_key) -> tuple[TicketHold, Payment]
def fulfill_ticket_hold(conn, payment) -> FulfillResult   # HELD->CONSUMED + issue N tickets, exactly once
def expire_holds(conn, as_of: str) -> int
def check_in(conn, event_id, code: str, staff_id: int) -> CheckInResult   # ISSUED->USED, ALREADY_USED otherwise
def refund_tickets(conn, payment) -> None
def event_report(conn, event_id) -> EventReport

# store/service.py (B)
def reserve_cart(conn, user_id, items: list[CartItem], idempotency_key) -> tuple[MerchOrder, Payment]  # all or nothing
def fulfill_merch_order(conn, payment) -> FulfillResult
def expire_orders(conn, as_of: str) -> int
def mark_picked_up(conn, order_id, staff_id) -> None
def refund_order(conn, payment) -> None

# journal/service.py (C) -- every money-moving service calls this on the SAME conn
def post_entry(conn, *, term_id, entry_date, source_type, source_id, source_event, memo,
               lines: list[Line]) -> int   # idempotent; balances validated in Python then re-checked by trigger
def reverse_entry(conn, entry_id: int, source_event: str, memo: str) -> int
def post_payment_received(conn, payment, *, fulfilled: bool) -> int
def post_settlement(conn, payment) -> int
def post_refund(conn, payment) -> int
def post_expense_approved(conn, expense) -> int
def post_expense_paid(conn, expense) -> int

# reports/service.py (C)
def cash_summary(conn, term_id) -> CashSummary
def income_expense(conn, term_id) -> IncomeExpense
def drilldown(conn, term_id, *, account_code=None, entry_id=None) -> DrillDown

# comms (C)
def publish_announcement(conn, announcement_id, actor_id) -> int       # enqueues mail
def subscribe(conn, email, user_id=None) -> Subscriber
def unsubscribe(conn, token) -> None
def process_mail_outbox(conn, limit: int = 100) -> int                 # writes mail_capture rows

# close/service.py, handover/service.py (C) -- see §10
def run_close(conn, term_id, actor_id) -> int
def run_handover(conn, term_id, from_user_id, to_user_id, role_codes, notes) -> int
```

**Payment-success transaction (single, owned by the webhook route / simulator route):**
```
with unit_of_work() as conn:
    outcome = payments.service.handle_event(conn, ...)      # validate -> update payment
      -> fulfill(conn, payment)                             # B's handler; same conn
      -> journal.post_payment_received(conn, payment, ...)  # C; same conn
```
Fulfillment and journal succeed or roll back together. A failing journal post aborts the fulfillment; the event is then retried with the same `event_id` (the failed attempt's `payment_events` row is rolled back with it).

**Hold consumption** releases held capacity exactly once because (a) `HELD→CONSUMED` is a guarded `UPDATE` requiring `rowcount == 1`, (b) the capacity query counts only `HELD`, and (c) tickets are inserted with `UNIQUE(hold_id)`.

**Merchandise reservation**: `reserve_cart` validates every line (`qty` 1–10, variant active, no duplicate variants), then for each line executes `UPDATE variants SET on_hand = on_hand - :q WHERE id=:id AND on_hand >= :q`; any `rowcount != 1` raises `INSUFFICIENT_STOCK` and the surrounding transaction rolls back the entire cart.

## 14. CLI commands (`python -m clubledger.cli …`, Owner A scaffolds, owners B/C register)

Each command opens its own `unit_of_work` and is idempotent; safe to run from cron/Task Scheduler every minute or manually.

| Command | Effect |
|---|---|
| `migrate` | applies `migrations/*.sql` in order, records in `schema_migrations` |
| `seed` | roles, permissions, accounts, plans, term, demo data (`--demo`) |
| `expire-holds` | `events.expire_holds` + `store.expire_orders` + payment `EXPIRED` for stale CREATED/PENDING; releases capacity/stock exactly once |
| `send-reminders [--as-of DATE]` | membership expiry (30 d, 7 d, expired) → enqueues `mail_outbox`; marks lapsed memberships `EXPIRED` |
| `process-mail [--limit N]` | `QUEUED`→`SENT`, writes `mail_capture`; no SMTP. Failures increment `attempts`, `FAILED` after 3 |
| `settle [--as-of DATE]` | simulated payout, posts settlement entries |
| `check-integrity` | runs §11 invariants; exit code 1 on failure |

## 15. Test and evidence conventions
Registered marker: `req(id)` in `pytest.ini` with `--strict-markers`; see REQUIREMENTS.md. `D` owns `evidence/` which records actual command outputs, pass/fail counts, and screenshot paths. Scores are never invented; if a check was not run, the evidence file states "not run".
