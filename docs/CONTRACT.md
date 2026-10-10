# ClubLedger Implementation Contract

Single club (Skyline Student Association). Python 3.12, FastAPI, Jinja2 + HTMX, SQLite (stdlib `sqlite3`, no ORM), plain SQL migrations. Local-first, no paid APIs. Documentation only: nothing here is implemented yet.

**UI/UX is deferred.** This contract fixes behavior, data, and permissions. Page layout and visual design are decided later; the screenshot supplied by the lead is a rough reference only and is not a requirement.

## 0. Global rules

| # | Rule |
|---|------|
| G1 | Money is `INTEGER` paise. Currency is fixed `INR`. No floats anywhere in money paths. Display formatting only in templates. |
| G2 | Prices, discounts, capacity, stock, and ownership are server-authoritative. Clients send IDs and quantities only, never amounts, prices, user IDs, or roles. |
| G3 | **Account ≠ membership.** A registered `users` row has no benefits. Benefits require an `ACTIVE` `memberships` row whose `[starts_at, expires_at)` covers the instant of purchase. Non-members buy at public price. Every purchase requires login. |
| G4 | **Time.** All stored timestamps are UTC ISO-8601 text `YYYY-MM-DDTHH:MM:SSZ`. Academic boundaries are computed in Asia/Kolkata (fixed offset `+05:30`; India has no DST, so no tz database dependency) and converted to UTC for storage. The single time source is `core.clock.now()`; see G9. |
| G5 | One connection per request. The route (or CLI command) owns the single outer transaction (`BEGIN IMMEDIATE` … `COMMIT`/`ROLLBACK`). Services take `conn` and **never** call `BEGIN`, `COMMIT`, or `ROLLBACK`. Nested transactions are forbidden. |
| G6 | SQLite pragmas on every connection: `foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`. |
| G7 | Every mutation is idempotent via a unique key (§6). Replays return the original result and write nothing. |
| G8 | Errors are typed: `DomainError(code, http_status)`. Codes are listed in §9. |
| G9 | **Clock injection.** `core/clock.py` exposes `now()`, `set_now(dt)`, `reset()`. `set_now` raises unless `CLUBLEDGER_ENV == "test"`. CLI `--as-of` is honored only when `CLUBLEDGER_ENV` is `dev` or `test`; otherwise it is rejected. No other module calls `datetime.now()`/`time.time()` (static test). |
| G10 | **Environments.** `CLUBLEDGER_ENV ∈ {dev, test, prod}`, default `dev`. The server binds `127.0.0.1` by default and refuses to start in `dev` bound to a non-loopback address. `prod` requires `CLUBLEDGER_SIM_SECRET` and `Secure` cookies. |
| G11 | **Schema conventions.** Every table is `STRICT`, has `id INTEGER PRIMARY KEY` (except pure join tables with composite keys) and `created_at TEXT NOT NULL` written by the service from `clock.now()` (no SQL default, so injected time is respected). Every foreign key is declared `REFERENCES` with `ON DELETE RESTRICT` unless stated. Only STRICT-legal types are used (`INTEGER`, `TEXT`, `REAL`, `BLOB`). Booleans are `INTEGER CHECK(x IN (0,1))`. |

## 1. Schema

Migration files are applied **strictly by number, contiguously**. File order of *writing* does not imply order of *applying*: `0006_journal.sql` may be written first by Owner C, but it is applied after `0001`–`0005`, and the migrator refuses to run if a number in `0001..0010` is missing. Owner A commits no-op placeholders (`-- reserved for <owner>`) for `0003`–`0010` at H0 so numbering is contiguous and the owners replace them. Every migration may reference only tables from lower-numbered migrations. Before the first merge to `master`, migrations may be edited and local DBs rebuilt with `reset-db` (dev only); the migrator stores a checksum per applied file and fails on mismatch with a message pointing to `reset-db`. After the first merge to `master`, applied migrations are frozen and changes require a new file.

### 1.1 Core / auth (Owner A, `0001_core.sql`)

```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  name TEXT NOT NULL,
  password_hash TEXT NOT NULL,                      -- hashlib.scrypt, per-user salt, encoded string
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  created_at TEXT NOT NULL
) STRICT;

CREATE TABLE roles (id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL) STRICT;
CREATE TABLE permissions (id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL) STRICT;
CREATE TABLE role_permissions (
  role_id INTEGER NOT NULL REFERENCES roles(id),
  permission_id INTEGER NOT NULL REFERENCES permissions(id),
  created_at TEXT NOT NULL,
  PRIMARY KEY (role_id, permission_id)
) STRICT;
CREATE TABLE user_roles (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  role_id INTEGER NOT NULL REFERENCES roles(id),
  granted_at TEXT NOT NULL,
  revoked_at TEXT,
  created_at TEXT NOT NULL
) STRICT;
CREATE UNIQUE INDEX ux_user_roles_live ON user_roles(user_id, role_id) WHERE revoked_at IS NULL;

CREATE TABLE sessions (
  id INTEGER PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,                  -- sha256 hex of a random 32-byte token; raw token only in the cookie
  user_id INTEGER NOT NULL REFERENCES users(id),
  csrf_token TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  idle_expires_at TEXT NOT NULL,                    -- sliding: min(last_seen_at + 2h, absolute_expires_at)
  absolute_expires_at TEXT NOT NULL,                -- created_at + 8h, never extended
  revoked_at TEXT,
  created_at TEXT NOT NULL
) STRICT;
CREATE INDEX ix_sessions_user ON sessions(user_id);

CREATE TABLE terms (                                 -- financial periods; NOT the membership year
  id INTEGER PRIMARY KEY,
  label TEXT NOT NULL UNIQUE,
  starts_at TEXT NOT NULL,                          -- UTC; inclusive
  ends_at TEXT,                                     -- UTC; exclusive; NULL while OPEN; set to the close instant
  status TEXT NOT NULL CHECK (status IN ('OPEN','CLOSED')),
  closed_at TEXT,
  created_at TEXT NOT NULL,
  CHECK ((status = 'OPEN' AND ends_at IS NULL AND closed_at IS NULL)
      OR (status = 'CLOSED' AND ends_at IS NOT NULL AND closed_at IS NOT NULL AND ends_at > starts_at))
) STRICT;
CREATE UNIQUE INDEX ux_terms_one_open ON terms(status) WHERE status = 'OPEN';   -- at most one OPEN term
-- Contiguity: close_term inserts the next term with starts_at = previous ends_at (same value, no gap, no overlap).

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY,
  actor_user_id INTEGER REFERENCES users(id),
  action TEXT NOT NULL, entity TEXT NOT NULL, entity_id INTEGER, detail TEXT,
  created_at TEXT NOT NULL
) STRICT;

CREATE TABLE idempotency_keys (                      -- browser double-submit protection (§6)
  actor_user_id INTEGER NOT NULL REFERENCES users(id),
  action TEXT NOT NULL,                              -- e.g. 'ticket.hold', 'store.reserve', 'membership.join'
  key TEXT NOT NULL,                                 -- server-issued uuid4 rendered into the form
  request_hash TEXT NOT NULL,                        -- sha256 of canonical request params
  result_ref TEXT NOT NULL,                          -- e.g. 'payment:123'
  created_at TEXT NOT NULL,
  PRIMARY KEY (actor_user_id, action, key)
) STRICT;

CREATE TABLE schema_migrations (
  number INTEGER PRIMARY KEY, filename TEXT NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL
) STRICT;
```

Rate limits are in-process and not stored (§4.4).

### 1.2 Payments (Owner A, `0002_payments.sql`)

```sql
CREATE TABLE payments (
  id INTEGER PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,                   -- opaque random id used in simulator URLs and events
  user_id INTEGER NOT NULL REFERENCES users(id),
  purpose TEXT NOT NULL CHECK (purpose IN ('DUES','TICKET','MERCH')),
  ref_table TEXT NOT NULL CHECK (ref_table IN ('memberships','ticket_holds','merch_orders')),
  ref_id INTEGER NOT NULL,                          -- polymorphic; validated by service, no SQL FK
  amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
  currency TEXT NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
  status TEXT NOT NULL CHECK (status IN ('CREATED','PENDING','SUCCEEDED','FAILED','EXPIRED','REFUNDED')),
  fulfillment TEXT NOT NULL DEFAULT 'NONE'
    CHECK (fulfillment IN ('NONE','FULFILLED','UNFULFILLED','RESOLVED_REFUNDED')),
  term_id INTEGER NOT NULL REFERENCES terms(id),    -- OPEN term when the payment was created; never changes
  succeeded_at TEXT, settled_at TEXT, refunded_at TEXT,
  created_at TEXT NOT NULL,
  CHECK (fulfillment <> 'FULFILLED' OR status IN ('SUCCEEDED','REFUNDED')),
  CHECK (fulfillment <> 'UNFULFILLED' OR status = 'SUCCEEDED')
) STRICT;
CREATE UNIQUE INDEX ux_payments_live_target ON payments(ref_table, ref_id)
  WHERE status IN ('CREATED','PENDING','SUCCEEDED');                      -- one live payment per target
CREATE INDEX ix_payments_user ON payments(user_id);
CREATE INDEX ix_payments_status ON payments(status, fulfillment);

CREATE TABLE payment_events (                       -- ONLY events that passed signature+timestamp+schema checks (§5)
  id INTEGER PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,                    -- gateway/simulator-issued, reserved only after signature is verified
  body_sha256 TEXT NOT NULL,                        -- detects event_id reuse with a different body
  raw_body TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('payment.succeeded','payment.failed')),
  payment_id INTEGER REFERENCES payments(id),       -- NULL when public_id did not resolve
  claimed_user_id INTEGER, claimed_public_id TEXT NOT NULL,
  amount_paise INTEGER NOT NULL, currency TEXT NOT NULL,
  outcome TEXT NOT NULL CHECK (outcome IN ('APPLIED','APPLIED_UNFULFILLED','UNAPPLIED_RECEIPT','NO_EFFECT')),
  reason TEXT,                                       -- e.g. 'AMOUNT_MISMATCH','UNKNOWN_PAYMENT','DUPLICATE_RECEIPT','LATE_AFTER_EXPIRED'
  settled_at TEXT,                                   -- for UNAPPLIED_RECEIPT booked to cash like a payment
  resolution TEXT CHECK (resolution IN ('REFUNDED','DISMISSED')),
  resolved_by INTEGER REFERENCES users(id), resolved_at TEXT, resolution_note TEXT,
  created_at TEXT NOT NULL,
  CHECK (outcome = 'UNAPPLIED_RECEIPT' OR resolution IS NULL)
) STRICT;
CREATE INDEX ix_payment_events_unresolved ON payment_events(outcome, resolution);
```
`outcome` is written once, when the row is inserted, and never updated (trigger `trg_payment_events_outcome_immutable`; only `settled_at` and the `resolution*` columns may change, and only for `UNAPPLIED_RECEIPT`).

### 1.3 Membership (Owner B, `0003_membership.sql`)

```sql
CREATE TABLE membership_plans (
  id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  dues_paise INTEGER NOT NULL CHECK (dues_paise > 0),
  ticket_discount_bps INTEGER NOT NULL CHECK (ticket_discount_bps BETWEEN 0 AND 10000),
  merch_discount_bps  INTEGER NOT NULL CHECK (merch_discount_bps  BETWEEN 0 AND 10000),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  created_at TEXT NOT NULL
) STRICT;

CREATE TABLE memberships (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  plan_id INTEGER NOT NULL REFERENCES membership_plans(id),
  membership_year TEXT NOT NULL,                    -- academic year label, e.g. '2026-27' (not a financial term)
  status TEXT NOT NULL CHECK (status IN ('PENDING','ACTIVE','EXPIRED','REVOKED','CANCELLED')),
  starts_at TEXT NOT NULL,                          -- UTC instant of 00:00 IST on the year's first day
  expires_at TEXT NOT NULL,                         -- exclusive; equals the next year's starts_at
  member_code TEXT UNIQUE,                          -- set on activation
  qr_token TEXT UNIQUE,                             -- set on activation
  payment_id INTEGER REFERENCES payments(id),
  verified_by INTEGER REFERENCES users(id), verified_at TEXT,
  created_at TEXT NOT NULL,
  CHECK (expires_at > starts_at),
  CHECK (status <> 'ACTIVE' OR (member_code IS NOT NULL AND qr_token IS NOT NULL))
) STRICT;
CREATE UNIQUE INDEX ux_member_user_year ON memberships(user_id, membership_year) WHERE status IN ('PENDING','ACTIVE');
CREATE INDEX ix_memberships_expiry ON memberships(status, expires_at);
```

**Membership year (not tied to financial close).** `core.clock.academic_year_bounds(instant) -> (label, starts_at_utc, expires_at_utc)`: the year runs 1 Aug 00:00 IST to the next 1 Aug 00:00 IST (stored e.g. `2026-07-31T18:30:00Z` → `2027-07-31T18:30:00Z`). Consecutive years are produced by the same function, so one year's `expires_at` equals the next year's `starts_at` exactly. A membership's validity is therefore independent of the financial term, and **closing a term (early or on time) never expires or changes any membership.** Renewal: allowed once `now >= expires_at − 30 days`; it creates a PENDING membership for the *next* membership year with `starts_at = current.expires_at`. It may be bought before the current term closes because it does not touch the term row; the payment posts to whichever term is OPEN at the time (cash basis, §7). `active_membership(at)` picks the ACTIVE row with `starts_at <= at < expires_at`.

There is no `reminders` table. Reminder deduplication uses `mail_outbox.dedupe_key` (§1.8).

### 1.4 Events & tickets (Owner B, `0004_events.sql`)

```sql
CREATE TABLE events (
  id INTEGER PRIMARY KEY,
  term_id INTEGER NOT NULL REFERENCES terms(id),    -- term in which the event was created (informational)
  title TEXT NOT NULL, venue TEXT NOT NULL, starts_at TEXT NOT NULL, ends_at TEXT NOT NULL,
  capacity INTEGER NOT NULL CHECK (capacity > 0),
  member_price_paise INTEGER NOT NULL CHECK (member_price_paise >= 0),
  public_price_paise INTEGER NOT NULL CHECK (public_price_paise >= member_price_paise),
  max_per_order INTEGER NOT NULL DEFAULT 4 CHECK (max_per_order BETWEEN 1 AND 10),
  status TEXT NOT NULL CHECK (status IN ('DRAFT','ON_SALE','CLOSED','CANCELLED')),
  created_at TEXT NOT NULL, CHECK (ends_at > starts_at)
) STRICT;

CREATE TABLE ticket_holds (
  id INTEGER PRIMARY KEY,
  event_id INTEGER NOT NULL REFERENCES events(id),
  user_id INTEGER NOT NULL REFERENCES users(id),
  qty INTEGER NOT NULL CHECK (qty BETWEEN 1 AND 10),
  unit_price_paise INTEGER NOT NULL CHECK (unit_price_paise >= 0),   -- frozen at hold time
  price_tier TEXT NOT NULL CHECK (price_tier IN ('MEMBER','PUBLIC')),
  status TEXT NOT NULL CHECK (status IN ('HELD','CONSUMED','RELEASED','EXPIRED')),
  expires_at TEXT NOT NULL, released_at TEXT, consumed_at TEXT,
  created_at TEXT NOT NULL
) STRICT;
CREATE INDEX ix_holds_event ON ticket_holds(event_id, status);
CREATE INDEX ix_holds_expiry ON ticket_holds(status, expires_at);

CREATE TABLE tickets (
  id INTEGER PRIMARY KEY,
  event_id INTEGER NOT NULL REFERENCES events(id),
  hold_id INTEGER NOT NULL REFERENCES ticket_holds(id),
  seat_index INTEGER NOT NULL CHECK (seat_index BETWEEN 1 AND 10),   -- 1..qty within the hold
  user_id INTEGER NOT NULL REFERENCES users(id),
  payment_id INTEGER REFERENCES payments(id),       -- NULL only for free tickets (unit price 0)
  code TEXT NOT NULL UNIQUE,                        -- opaque QR payload: 16 random bytes, base32
  price_paise INTEGER NOT NULL CHECK (price_paise >= 0),   -- this seat's frozen price
  price_tier TEXT NOT NULL CHECK (price_tier IN ('MEMBER','PUBLIC')),
  status TEXT NOT NULL CHECK (status IN ('ISSUED','USED','REFUNDED','VOID')),
  used_at TEXT, used_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  UNIQUE (hold_id, seat_index),                     -- N tickets per hold, each seat exactly once
  CHECK ((status = 'USED') = (used_at IS NOT NULL)),
  CHECK (price_paise = 0 OR payment_id IS NOT NULL),
  CHECK (status <> 'VOID' OR payment_id IS NULL)    -- VOID exists only for free tickets (event cancellation)
) STRICT;
CREATE INDEX ix_tickets_event ON tickets(event_id, status);
CREATE INDEX ix_tickets_user ON tickets(user_id);
CREATE INDEX ix_tickets_payment ON tickets(payment_id);
```

**Seats.** A hold of `qty = N` yields exactly N `tickets` rows with `seat_index = 1..N`. Payment amount = `N × unit_price_paise`, and each ticket stores `unit_price_paise` in `price_paise`. Exactly-once is guaranteed by two independent guards: the guarded transition `UPDATE ticket_holds SET status='CONSUMED' WHERE id=? AND status='HELD'` (must affect 1 row, else the transaction aborts) **and** `UNIQUE(hold_id, seat_index)`.

**Capacity invariant** (checked inside `BEGIN IMMEDIATE`): `Σ qty of HELD holds with expires_at > now  +  count(tickets WHERE status IN ('ISSUED','USED'))  <= events.capacity`. `available_seats = capacity − that sum`.

### 1.5 Store (Owner B, `0005_store.sql`)

```sql
CREATE TABLE products (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
  base_price_paise INTEGER NOT NULL CHECK (base_price_paise > 0),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)), created_at TEXT NOT NULL
) STRICT;

CREATE TABLE variants (
  id INTEGER PRIMARY KEY,
  product_id INTEGER NOT NULL REFERENCES products(id),
  sku TEXT NOT NULL UNIQUE, size TEXT NOT NULL,
  physical_qty INTEGER NOT NULL CHECK (physical_qty >= 0),   -- units the club physically holds; changes only by staff restock/adjust and by pickup
  reserved_qty INTEGER NOT NULL DEFAULT 0 CHECK (reserved_qty >= 0),   -- units promised to RESERVED or PAID-not-yet-picked-up orders
  created_at TEXT NOT NULL,
  UNIQUE (product_id, size),
  CHECK (reserved_qty <= physical_qty)
) STRICT;
-- available = physical_qty - reserved_qty   (the only number shown to shoppers)

CREATE TABLE merch_orders (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  status TEXT NOT NULL CHECK (status IN ('RESERVED','PAID','PICKED_UP','CANCELLED','EXPIRED','REFUNDED')),
  expires_at TEXT NOT NULL, total_paise INTEGER NOT NULL CHECK (total_paise >= 0),
  price_tier TEXT NOT NULL CHECK (price_tier IN ('MEMBER','PUBLIC')),
  payment_id INTEGER REFERENCES payments(id),
  picked_up_at TEXT, picked_up_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
) STRICT;
CREATE INDEX ix_orders_user ON merch_orders(user_id);
CREATE INDEX ix_orders_expiry ON merch_orders(status, expires_at);

CREATE TABLE merch_order_items (
  id INTEGER PRIMARY KEY,
  order_id INTEGER NOT NULL REFERENCES merch_orders(id),
  variant_id INTEGER NOT NULL REFERENCES variants(id),
  qty INTEGER NOT NULL CHECK (qty BETWEEN 1 AND 10),
  unit_price_paise INTEGER NOT NULL CHECK (unit_price_paise > 0),
  created_at TEXT NOT NULL,
  UNIQUE (order_id, variant_id)
) STRICT;
```

**Stock terminology.** *Physical* stock = `physical_qty`. *Reserved* = `reserved_qty`. *Available* = physical − reserved. Reserve: `UPDATE variants SET reserved_qty = reserved_qty + :q WHERE id = :id AND physical_qty - reserved_qty >= :q` (must affect 1 row). Expire/cancel/refund-before-pickup: `reserved_qty -= q` (exactly once, guarded by the order status transition). Pickup: `reserved_qty -= q` **and** `physical_qty -= q` in the same transaction. Staff restock/adjust changes only `physical_qty` (never below `reserved_qty`).

### 1.6 Journal (Owner C writes first, `0006_journal.sql`; applied after 0001–0005)

```sql
CREATE TABLE accounts (
  id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('ASSET','LIABILITY','INCOME','EXPENSE')),
  created_at TEXT NOT NULL
) STRICT;

CREATE TABLE journal_entries (
  id INTEGER PRIMARY KEY,
  term_id INTEGER NOT NULL REFERENCES terms(id),    -- must be the OPEN term (trigger)
  entry_date TEXT NOT NULL,                         -- UTC instant the effect is recognized; used for as-of balances
  source_type TEXT NOT NULL CHECK (source_type IN ('payment','payment_event','expense','adjustment')),
  source_id INTEGER NOT NULL,
  source_event TEXT NOT NULL,                       -- 'received','fulfilled_late','settled','approved','paid','<x>_reversal', 'adjustment'
  memo TEXT,
  status TEXT NOT NULL CHECK (status IN ('DRAFT','POSTED')),
  posted_at TEXT,
  reverses_entry_id INTEGER REFERENCES journal_entries(id),
  adjusts_term_id INTEGER REFERENCES terms(id),     -- informational: which CLOSED term an adjustment corrects
  created_at TEXT NOT NULL,
  UNIQUE (source_type, source_id, source_event),
  CHECK ((status = 'POSTED') = (posted_at IS NOT NULL)),
  CHECK (adjusts_term_id IS NULL OR adjusts_term_id <> term_id),
  CHECK (adjusts_term_id IS NULL OR source_type = 'adjustment'),
  CHECK (source_event NOT LIKE '%_reversal' OR reverses_entry_id IS NOT NULL)
) STRICT;
CREATE INDEX ix_entries_term ON journal_entries(term_id, entry_date);
CREATE INDEX ix_entries_asof ON journal_entries(status, entry_date);
CREATE INDEX ix_entries_source ON journal_entries(source_type, source_id);
CREATE UNIQUE INDEX ux_entries_reversal ON journal_entries(reverses_entry_id) WHERE reverses_entry_id IS NOT NULL;  -- reverse at most once

CREATE TABLE journal_lines (
  id INTEGER PRIMARY KEY,
  entry_id INTEGER NOT NULL REFERENCES journal_entries(id),
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  debit_paise INTEGER NOT NULL DEFAULT 0 CHECK (debit_paise >= 0),
  credit_paise INTEGER NOT NULL DEFAULT 0 CHECK (credit_paise >= 0),
  created_at TEXT NOT NULL,
  CHECK ((debit_paise = 0) <> (credit_paise = 0))   -- exactly one side non-zero
) STRICT;
CREATE INDEX ix_lines_entry ON journal_lines(entry_id);
CREATE INDEX ix_lines_account ON journal_lines(account_id);
```

**Protection triggers (the database enforces these, not only code).** Entries are created as `DRAFT`, lines are added, then the entry is flipped to `POSTED` exactly once.

| Trigger | Fires | Rule |
|---|---|---|
| `trg_entry_insert_draft_only` | BEFORE INSERT on `journal_entries` | `status` must be `'DRAFT'` (a direct INSERT of a `POSTED` entry — valid or not — aborts). Also: `term_id` must reference a term with `status='OPEN'` (`TERM_CLOSED`). |
| `trg_entry_post_check` | BEFORE UPDATE OF `status` on `journal_entries` WHEN `NEW.status='POSTED'` | `OLD.status` must be `DRAFT`; line count ≥ 2; `Σdebit = Σcredit` and > 0; the entry's `term_id` is still `OPEN`; abort otherwise. |
| `trg_entry_immutable_posted` | BEFORE UPDATE or DELETE on `journal_entries` WHEN `OLD.status='POSTED'` | always abort. |
| `trg_entry_term_fixed` | BEFORE UPDATE OF `term_id`, `source_type`, `source_id`, `source_event`, `reverses_entry_id` on `journal_entries` | always abort (key fields never change even in DRAFT). |
| `trg_line_insert_draft_only` | BEFORE INSERT on `journal_lines` | the parent entry must exist and be `DRAFT` (no insertion into a posted entry). |
| `trg_line_update_blocked` | BEFORE UPDATE on `journal_lines` | abort if the **old** parent or the **new** parent is `POSTED` (blocks editing lines of, moving lines into, and moving lines out of a posted entry); `entry_id` may never change at all. |
| `trg_line_delete_draft_only` | BEFORE DELETE on `journal_lines` | abort if the parent is `POSTED`. |

**No closed-term bypass.** There is no exception for `adjusts_term_id` or any other column. Every entry, including adjustments, belongs to the **OPEN** term (`term_id`); `adjusts_term_id` only records which closed term is being corrected and is rejected unless that term is `CLOSED`.

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

### 1.7 Fundraisers and tasks (Owner C, `0007_tasks.sql`)

Fundraisers/tasks precede expenses because expenses link to them.

```sql
CREATE TABLE fundraisers (
  id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL REFERENCES terms(id), title TEXT NOT NULL,
  goal_paise INTEGER CHECK (goal_paise IS NULL OR goal_paise > 0),
  status TEXT NOT NULL CHECK (status IN ('PLANNING','ACTIVE','DONE','CANCELLED')), created_at TEXT NOT NULL
) STRICT;
CREATE TABLE tasks (
  id INTEGER PRIMARY KEY,
  fundraiser_id INTEGER NOT NULL REFERENCES fundraisers(id),
  title TEXT NOT NULL,
  owner_user_id INTEGER REFERENCES users(id),
  due_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('TODO','DOING','DONE','BLOCKED')),
  created_at TEXT NOT NULL,
  UNIQUE (id, fundraiser_id)                         -- target for the composite FK below
) STRICT;
```

### 1.8 Expenses and receipts (Owner C, `0008_expenses.sql`)

```sql
CREATE TABLE expenses (
  id INTEGER PRIMARY KEY,
  submitter_id INTEGER NOT NULL REFERENCES users(id),
  term_id INTEGER NOT NULL REFERENCES terms(id),    -- OPEN term at submission
  category_account_id INTEGER NOT NULL REFERENCES accounts(id),   -- service verifies code is in 5000-5099
  amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
  description TEXT NOT NULL,
  event_id INTEGER REFERENCES events(id),
  fundraiser_id INTEGER REFERENCES fundraisers(id),
  task_id INTEGER,
  status TEXT NOT NULL CHECK (status IN ('SUBMITTED','APPROVED','REJECTED','PAID','VOID')),
  decided_by INTEGER REFERENCES users(id), decided_at TEXT, decision_note TEXT,
  paid_by INTEGER REFERENCES users(id), paid_at TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (task_id, fundraiser_id) REFERENCES tasks(id, fundraiser_id),   -- a task link requires its own fundraiser
  CHECK (task_id IS NULL OR fundraiser_id IS NOT NULL)
) STRICT;
CREATE INDEX ix_expenses_status ON expenses(status);

CREATE TABLE receipts (
  id INTEGER PRIMARY KEY,
  uploader_id INTEGER NOT NULL REFERENCES users(id),
  expense_id INTEGER NOT NULL REFERENCES expenses(id),
  stored_name TEXT NOT NULL UNIQUE,                  -- random name in a directory outside static files
  original_name TEXT NOT NULL,
  mime TEXT NOT NULL CHECK (mime IN ('image/png','image/jpeg','application/pdf')),
  size_bytes INTEGER NOT NULL CHECK (size_bytes BETWEEN 1 AND 5242880),
  sha256 TEXT NOT NULL, created_at TEXT NOT NULL
) STRICT;
CREATE INDEX ix_receipts_expense ON receipts(expense_id);
```
An expense is created first, then receipts are attached to it (receipts are never orphaned).

### 1.9 Comms (Owner C, `0009_comms.sql`)

```sql
CREATE TABLE announcements (
  id INTEGER PRIMARY KEY, author_id INTEGER NOT NULL REFERENCES users(id), term_id INTEGER NOT NULL REFERENCES terms(id),
  title TEXT NOT NULL, body TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('DRAFT','PUBLISHED')), published_at TEXT, created_at TEXT NOT NULL,
  CHECK ((status = 'PUBLISHED') = (published_at IS NOT NULL))
) STRICT;
CREATE TABLE subscribers (
  id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  user_id INTEGER REFERENCES users(id),
  status TEXT NOT NULL CHECK (status IN ('SUBSCRIBED','UNSUBSCRIBED')),
  unsub_token TEXT NOT NULL UNIQUE, subscribed_at TEXT NOT NULL, unsubscribed_at TEXT, created_at TEXT NOT NULL
) STRICT;
CREATE TABLE mail_outbox (
  id INTEGER PRIMARY KEY,
  dedupe_key TEXT NOT NULL UNIQUE,                   -- always non-NULL, so duplicates cannot slip past UNIQUE
  to_email TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('ANNOUNCEMENT','RENEW_30D','RENEW_7D','EXPIRED')),
  ref_table TEXT NOT NULL CHECK (ref_table IN ('announcements','memberships')),
  ref_id INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('QUEUED','SENT','FAILED','SUPPRESSED')),
  suppressed_reason TEXT,                            -- 'UNSUBSCRIBED','MEMBERSHIP_RENEWED','MEMBERSHIP_REVOKED','USER_INACTIVE'
  attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, processed_at TEXT, created_at TEXT NOT NULL,
  CHECK ((status = 'SUPPRESSED') = (suppressed_reason IS NOT NULL))
) STRICT;
CREATE INDEX ix_outbox_status ON mail_outbox(status);
CREATE TABLE mail_capture (
  id INTEGER PRIMARY KEY,
  outbox_id INTEGER NOT NULL UNIQUE REFERENCES mail_outbox(id),   -- exactly one capture per message
  to_email TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL, captured_at TEXT NOT NULL, created_at TEXT NOT NULL
) STRICT;
```
`dedupe_key` formats: `announcement:{announcement_id}:{lower(email)}`; `reminder:{kind}:{membership_id}`.

### 1.10 Close and handover (Owner C, `0010_close.sql`)

```sql
CREATE TABLE close_snapshots (
  id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL UNIQUE REFERENCES terms(id),
  taken_at TEXT NOT NULL, taken_by INTEGER NOT NULL REFERENCES users(id),
  totals_json TEXT NOT NULL, content_sha256 TEXT NOT NULL, created_at TEXT NOT NULL
) STRICT;                                            -- triggers: BEFORE UPDATE / DELETE -> RAISE(ABORT)
CREATE TABLE close_checks (
  id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL REFERENCES terms(id), code TEXT NOT NULL,
  passed INTEGER NOT NULL CHECK (passed IN (0,1)), detail TEXT, evaluated_at TEXT NOT NULL, created_at TEXT NOT NULL
) STRICT;                                            -- written only by a SUCCESSFUL close; failing runs return checks without writing
CREATE TABLE officer_handover (
  id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL UNIQUE REFERENCES terms(id),
  from_user_id INTEGER NOT NULL REFERENCES users(id), to_user_id INTEGER NOT NULL REFERENCES users(id),
  notes TEXT, role_changes_json TEXT NOT NULL, completed_at TEXT NOT NULL, created_at TEXT NOT NULL
) STRICT;
```

**Apply order = number order:** 0001 core → 0002 payments → 0003 membership → 0004 events → 0005 store → 0006 journal → 0007 tasks → 0008 expenses → 0009 comms → 0010 close. Dependencies check: 0003→(users, payments); 0004→(terms, users, payments); 0005→users, payments; 0006→terms; 0007→terms, users; 0008→terms, users, accounts(0006), events(0004), fundraisers/tasks(0007); 0009→users, terms; 0010→terms, users. `payments` and `payment_events` (0002) use no FK to 0003–0005.

## 2. Pricing and entitlement rules (shared, `core/pricing.py`, Owner A)

- `active_membership(conn, user_id, at) -> Membership | None`: `status='ACTIVE'` and `starts_at <= at < expires_at`.
- Price tier is decided **server-side at hold/reserve time** and frozen on the hold/order. Later membership changes do not reprice.
- Ticket unit price: `MEMBER` → `min(events.member_price_paise, public_price_paise * (10000 - ticket_discount_bps) // 10000)` (a plan can improve but never worsen the event's member price). `PUBLIC` → `public_price_paise`.
- Merch unit price: `base_price_paise * (10000 - merch_discount_bps) // 10000` (floor, integer arithmetic) for members, else base.
- Dues price: `membership_plans.dues_paise` at purchase, frozen in `payments.amount_paise`.
- **Free tickets (unit price 0):** require login and capacity like any ticket; no payment, no journal entry. `create_hold` inserts the hold directly as `CONSUMED`, issues the N tickets with `payment_id NULL` in the same transaction, and returns no payment. They cannot be refunded; on event cancellation they become `VOID`.
- **Events of closed terms:** `events.term_id` is informational. An `ON_SALE` event created in a now-closed term remains purchasable until it ends or is closed/cancelled. New holds/payments carry the **OPEN** term; income posts to the OPEN term (§7). Event reports span all terms (§11).

## 3. State machines

### 3.1 Payment (`payments.status`) and fulfillment (`payments.fulfillment`)

`status` (money truth):

```
CREATED  --simulator opens page--------------------------> PENDING
CREATED/PENDING --valid payment.succeeded, target live---> SUCCEEDED (+ fulfillment FULFILLED)
CREATED/PENDING --valid payment.succeeded, target not live or handler returns UNFULFILLABLE--> SUCCEEDED (+ UNFULFILLED)
CREATED/PENDING --payment.failed-------------------------> FAILED
CREATED/PENDING --expire-holds command (>30 min / target expired)--> EXPIRED
FAILED  --valid payment.succeeded (late)-----------------> SUCCEEDED (+ UNFULFILLED; never auto-fulfilled)
EXPIRED --valid payment.succeeded (late)-----------------> SUCCEEDED (+ UNFULFILLED; never auto-fulfilled)
SUCCEEDED --full refund----------------------------------> REFUNDED
```
`SUCCEEDED` and `REFUNDED` never go back. `FAILED`/`EXPIRED` mean "nothing received **so far**"; they accept a later *verified* success so verified money is never dropped.

`fulfillment` (what we owe in return): `NONE` → `FULFILLED` | `UNFULFILLED`; `UNFULFILLED` → `FULFILLED` (staff manual fulfill) | `RESOLVED_REFUNDED`. A fulfilled payment that is refunded keeps `fulfillment='FULFILLED'` and `status='REFUNDED'`.

**Valid-success matrix** (a *valid* success event has passed §5 steps 1–8):

| Payment before | Target / term | Result | Journal (OPEN term) |
|---|---|---|---|
| CREATED/PENDING | target live (hold `HELD`, order `RESERVED`, membership `PENDING`) and handler fulfills | SUCCEEDED + FULFILLED, outcome `APPLIED` | `received` Dr 1100 / Cr income |
| CREATED/PENDING | target no longer live, or handler returns UNFULFILLABLE (capacity/stock/year conflict) | SUCCEEDED + UNFULFILLED, `APPLIED_UNFULFILLED` | `received` Dr 1100 / Cr 2000 |
| EXPIRED | any | SUCCEEDED + UNFULFILLED, `APPLIED_UNFULFILLED`, reason `LATE_AFTER_EXPIRED` | Dr 1100 / Cr 2000 |
| FAILED | any (prior failure) | SUCCEEDED + UNFULFILLED, `APPLIED_UNFULFILLED`, reason `LATE_AFTER_FAILED` | Dr 1100 / Cr 2000 |
| any, payment's `term_id` is a **CLOSED** term (only EXPIRED/FAILED can exist there) | — | same as the EXPIRED/FAILED rows; fulfillment is not attempted | posts to the **OPEN** term with memo "prior-term payment {term label}" |
| SUCCEEDED / REFUNDED (a second success for the same payment) | — | outcome `UNAPPLIED_RECEIPT`, reason `DUPLICATE_RECEIPT`; payment row unchanged | `payment_event` entry Dr 1100 / Cr 2000 |
| any, but identity/amount/currency does not match, or `public_id` unknown | — | outcome `UNAPPLIED_RECEIPT` (reason `AMOUNT_MISMATCH`, `CURRENCY_MISMATCH`, `USER_MISMATCH`, `UNKNOWN_PAYMENT`); payment row unchanged | if `currency='INR'` and `amount>0`: Dr 1100 / Cr 2000 for the event's amount, else none |

`payment.failed` events: apply `CREATED/PENDING → FAILED` (outcome `APPLIED`); for any other payment state, or when identity/amount/currency do not match, outcome `NO_EFFECT` with a reason (a failure event moves no money and is never booked).

**Resolution path (nothing stays unresolved).** Every `UNFULFILLED` payment and every unresolved `UNAPPLIED_RECEIPT` appears in `/admin/payments?problem=1` and **blocks term close** (§10).
- `UNFULFILLED` payment: `payments.service.resolve_unfulfilled(conn, handlers, payment_id, action, actor_id)` with `action ∈ {REFUND, FULFILL}`.
  - `REFUND`: full refund (§8), `fulfillment → RESOLVED_REFUNDED`. Always allowed.
  - `FULFILL`: allowed only if `payment.term_id` is the OPEN term **and** the purpose handler can still grant (tickets: `EXPIRED` hold → `CONSUMED` if capacity is free, which re-checks the capacity invariant; merch: order `EXPIRED` → re-reserve stock → `PAID`; dues: membership `CANCELLED` → `ACTIVE` if no live membership exists for that year). On success `fulfillment → FULFILLED`, journal `fulfilled_late` Dr 2000 / Cr income. If the handler cannot grant, `SOLD_OUT`/`INSUFFICIENT_STOCK`/`ALREADY_MEMBER` is returned and the obligation remains (refund is then the only path).
- `UNAPPLIED_RECEIPT` event: `payments.service.resolve_receipt(conn, event_row_id, action, actor_id, note)` with `action ∈ {REFUND, DISMISS}`. `REFUND`: reverses its entries (and settlement entry if settled), sets `resolution='REFUNDED'`. `DISMISS` (staff attests that no money was actually received; `note` required): reverses its entries, `resolution='DISMISSED'`. Non-INR or zero-amount events have no entries; they still need a resolution.

### 3.2 Membership
`PENDING` (dues unpaid) → `ACTIVE` (dues fulfilled) → `EXPIRED` (`send-reminders` finds `expires_at <= now`) | `REVOKED` (full refund or admin). `PENDING` → `CANCELLED` (user cancels, or `expire-holds` after its payment `EXPIRED`). Renewal rule is in §1.3. Term close never changes membership status.

### 3.3 Ticket hold / ticket
Hold: `HELD` → `CONSUMED` (payment fulfilled, or free ticket at creation) | `RELEASED` (user cancel) | `EXPIRED` (`expire-holds`, TTL 10 min). A manual `FULFILL` of an `UNFULFILLED` payment may move `EXPIRED` → `CONSUMED` (capacity re-checked).
Ticket: `ISSUED` → `USED` (check-in) | `REFUNDED` (full refund of its payment). `VOID` applies only to **free** tickets of a cancelled event.
Capacity release rule: converting a hold to tickets in one transaction removes the `HELD` quantity from the held term (status becomes `CONSUMED`) and adds the same number of `ISSUED` tickets, so held capacity is released exactly once (§1.4 guards).

**Event cancellation** (`events.cancel_event`): event → `CANCELLED`, sales stop; each paid payment whose tickets are all `ISSUED` is fully refunded through the normal refund path (tickets → `REFUNDED`, not `VOID`); free tickets → `VOID`; any payment with a `USED` ticket is **not** refunded and is listed for manual review.

### 3.4 Merch order
`RESERVED` (reserved_qty incremented, TTL 15 min) → `PAID` → `PICKED_UP`; `RESERVED` → `EXPIRED`/`CANCELLED` (reserved restored); `PAID` → `REFUNDED` (reserved restored). `PICKED_UP` is terminal and cannot be refunded.

### 3.5 Expense
`SUBMITTED` → `APPROVED` | `REJECTED`; `APPROVED` → `PAID`; `SUBMITTED` → `VOID` (by submitter). Approver ≠ submitter. `PAID` terminal. Pay requires ≥ 1 receipt.

### 3.6 Announcement
`DRAFT` → `PUBLISHED` (enqueues one `mail_outbox` row per `SUBSCRIBED` subscriber via `dedupe_key`). Published announcements are not editable.

### 3.7 Term
`OPEN` → `CLOSED` inside the close transaction only; the next `OPEN` term is inserted in that same transaction with `starts_at` equal to the closed term's `ends_at`.

## 4. Auth, sessions, CSRF, permissions, limits

### 4.1 Sessions
- Login: verify scrypt hash, create a `sessions` row (`absolute_expires_at = now + 8h`, `idle_expires_at = now + 2h`, `last_seen_at = now`), cookie `cl_session=<raw token>` (`HttpOnly`, `SameSite=Lax`, `Secure` when `CLUBLEDGER_ENV=prod`, `Path=/`).
- A request is valid iff `revoked_at IS NULL AND now < idle_expires_at AND now < absolute_expires_at`. Sliding refresh: if `now - last_seen_at >= 60 s`, set `last_seen_at = now` and `idle_expires_at = min(now + 2h, absolute_expires_at)`. `absolute_expires_at` never changes.
- Logout sets `revoked_at`; any request using it gets 401 and the cookie is cleared.
- **Authorization is re-read from the DB on every request** (`user_roles.revoked_at IS NULL` joined through `role_permissions`). Nothing is cached in the cookie or process memory, so role revocation is immediate.
- Deactivating a user (`is_active=0`) revokes all their sessions in the same transaction.

### 4.2 CSRF
- Per-session `csrf_token`. Every browser `POST/PUT/PATCH/DELETE` must send it as form field `csrf_token` or header `X-CSRF-Token` (HTMX sets it once in `hx-headers` on `<body>`). Constant-time compare. Missing/invalid → 403 `CSRF_FAILED`.
- **Exemption (documented, single route):** `POST /webhooks/payments` has no cookie session and is authenticated solely by the HMAC signature (§5). No other route is exempt.
- Unauthenticated state-changing routes (`/auth/register`, `/auth/login`, `/subscribe`, `/unsubscribe/{token}`) use a pre-session double-submit CSRF cookie `cl_csrf`.
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

Members (plain users) have no staff permissions. `comms.mail_viewer` and `receipts.view_all` are never implied by other roles. A receipt's uploader can always view their own receipt.

### 4.4 Rate limits and developer routes
- In-process token buckets (single worker; reset on restart), keyed on the injected clock (G9), return 429 `RATE_LIMITED` with `Retry-After`. Limits: login 5/min per (client IP, email); register 10/hour per IP; `/subscribe` 10/hour per IP; `/webhooks/payments` 60/min per IP (also applied *before* signature verification, so floods cannot write to the DB); `/verify/lookup` 60/min per user; `/checkin/*/scan` 120/min per user.
- **Developer routes** (`/dev/mail`, `/dev/mail/{id}`) are registered only when `CLUBLEDGER_ENV ∈ {dev,test}` (in `prod` they do not exist → 404) **and** additionally require `comms.mail_viewer` and an authenticated session. The server in `dev` only listens on loopback (G10).

## 5. Payment simulator and webhook

Local simulator, no network. `payments/simulator.py`:
- `POST /pay/{public_id}/outcome` (browser, session + CSRF + ownership): field `outcome ∈ {success, fail}`. The server builds the event body, assigns a fresh `event_id`, and **signs it server-side**: `sig = HMAC_SHA256(SIM_SECRET, f"{timestamp}.{raw_body}")`, then calls the same `payments.webhook.handle_event(...)` used by the HTTP webhook. The browser never sees the secret or signature.
- `POST /webhooks/payments` (external-shaped; used by tests and `scripts/sim_webhook.py`). Header `X-Signature: t=<unix>,v1=<hex>`.
- Event JSON: `{"event_id","type":"payment.succeeded|payment.failed","payment_id":"<public_id>","user_id":int,"amount_paise":int,"currency":"INR"}`.
- `SIM_SECRET` from env `CLUBLEDGER_SIM_SECRET`; in `dev`/`test` a random secret is generated once into `data/.sim_secret` (gitignored); `prod` refuses to start without it.

**Rejection and dedupe boundary.** Nothing is written to the database for an event until its signature has been verified, so unauthenticated callers can neither write rows nor reserve `event_id`s.

1. *Untrusted phase (no DB write):* rate limit (§4.4) → header parse → timestamp window (`|now − t| ≤ 300 s`) → HMAC verify (constant time) → JSON schema/size (≤ 4 KB). Any failure → HTTP 400 `BAD_SIGNATURE`/`VALIDATION`, **zero database writes** (including the audit log). The failure is recorded only in the application log file (`logging`, not SQLite) with remote IP and reason.
2. *Trusted phase (inside the unit of work):* look up `event_id`.
   - Found with the same `body_sha256` → **duplicate**: return HTTP 200 with the *original stored outcome*, write nothing, never update the stored row.
   - Found with a different `body_sha256` → HTTP 409 `EVENT_ID_REUSED`, no mutation, logged.
   - Not found → evaluate §3.1 in order: (a) payment lookup by `public_id`; (b) `user_id` matches; (c) currency `INR`; (d) amount equals `amount_paise`; (e) apply the matrix. Insert the `payment_events` row (with its final `outcome`) in the same transaction as every state change, so a rollback also removes the row and a retry of the same `event_id` is processed fresh.

Because the row carries its outcome from the moment it exists and `outcome` is immutable, a replay can never overwrite a prior result.

## 6. Idempotency & uniqueness keys

| Effect | Key |
|--------|-----|
| Webhook event | `payment_events.event_id` UNIQUE (trusted events only) + `body_sha256` |
| Payment received journal | `journal_entries(source_type='payment', source_id=payment.id, source_event='received')` |
| Late fulfillment journal | `(…, 'fulfilled_late')` |
| Settlement journal | `(…, 'settled')` |
| Reversal of any entry | `ux_entries_reversal` on `reverses_entry_id`; `source_event = '<original>_reversal'` |
| Unapplied receipt | `(source_type='payment_event', source_id=event row id, 'received')` and `('settled')`, reversals as above |
| Expense effects | `(source_type='expense', source_id, 'approved' | 'paid')` |
| Fulfillment | guarded status `UPDATE` with `rowcount == 1`; `payments.fulfillment` leaves `NONE`/`UNFULFILLED` once |
| Mail | `mail_outbox.dedupe_key` UNIQUE NOT NULL; `mail_capture.outbox_id` UNIQUE |
| Browser double-submit | `idempotency_keys` PK `(actor_user_id, action, key)`; a repeat with the same `request_hash` returns the original `result_ref`; the same key with a different `request_hash` → 422 `IDEMPOTENCY_CONFLICT`; a key belonging to another actor or action is never visible or reusable |

`post_entry` returns the existing `entry_id` when the unique key already exists (`INSERT … ON CONFLICT DO NOTHING`, then select) and posts nothing.

## 7. Journal posting patterns

Every entry's `term_id` = the **OPEN** term at posting time (cash basis: income is recognized when money is received, in the term in which it is received, regardless of which term the payment was created in or which membership year/event it buys). `entry_date` = injected `now`.

| Event | Debit | Credit |
|-------|-------|--------|
| Payment succeeded + fulfilled (`received`) | 1100 Clearing | 4000 / 4100 / 4200 |
| Payment succeeded + unfulfilled (`received`) | 1100 Clearing | 2000 Unfulfilled Obligation |
| Obligation later fulfilled (`fulfilled_late`) | 2000 | 4000 / 4100 / 4200 |
| Unapplied receipt (`received`, source `payment_event`) | 1100 | 2000 |
| **Settlement** (`settled`; `cli settle`: every `SUCCEEDED` payment and `UNAPPLIED_RECEIPT` event not yet settled whose `succeeded_at`/`created_at` is ≥ 1 day before `as-of`; full amount, no fees) | 1000 Cash | 1100 Clearing |
| Expense approved | 50xx category | 2100 Reimbursements Payable |
| Expense paid (reimbursement) | 2100 | 1000 Cash |
| Adjustment (`source_type='adjustment'`, memo required) | caller-specified, balanced | |

**Reversals are exact mirrors.** `reverse_entry(original)` posts a new entry whose lines are the original's with debit/credit swapped, `reverses_entry_id = original.id`, `source_event = '<original source_event>_reversal'`, in the OPEN term. A **full refund** reverses *every not-yet-reversed entry of that payment (or payment_event), newest first*:
- not settled: reverse `received` (and `fulfilled_late` first, if present) → `received_reversal` credits 1100;
- settled: additionally reverse `settled` → `settled_reversal` (Dr 1100 / Cr 1000). Net effect on 1100 is zero and cash falls by the refunded amount.
There is no ad-hoc "refund entry" with custom accounts; refund effects are only these exact reversals.

## 8. Refund rules (full refunds only)
`refund_payment(conn, handlers, payment_id, actor_id)`:
- Requires `payments.admin`. Payment must be `SUCCEEDED` (not `REFUNDED`, `FAILED`, `EXPIRED`). No amount parameter exists.
- Eligibility depends on `fulfillment`:
  - `UNFULFILLED`: **always eligible**; no ticket/order/membership state is checked (there is none to check). Reverses its entries; `fulfillment → RESOLVED_REFUNDED`.
  - `FULFILLED`: purpose handler `check_refundable` then `apply_refund`:
    - DUES: membership → `REVOKED`; discount entitlement ends immediately (the resolver requires `ACTIVE`). Tickets/merch already bought at member price are not clawed back.
    - TICKET: **all** tickets of the payment must be `ISSUED`; if any is `USED` → `REFUND_BLOCKED`. Otherwise all → `REFUNDED` and their seats stop counting toward capacity. Seats cannot be refunded individually.
    - MERCH: order must be `PAID`; `PICKED_UP` → `REFUND_BLOCKED`. Order → `REFUNDED`, `reserved_qty` restored.
- Journal: exact reversals (§7). `payments.status → REFUNDED`, `refunded_at` set.
- A refund after the payment's term closed is allowed; its reversal entries post in the OPEN term.

## 9. Error codes
`AUTH_REQUIRED(401)`, `FORBIDDEN(403)`, `CSRF_FAILED(403)`, `NOT_FOUND(404)`, `VALIDATION(422)`, `SOLD_OUT(409)`, `INSUFFICIENT_STOCK(409)`, `HOLD_EXPIRED(409)`, `ALREADY_MEMBER(409)`, `BAD_SIGNATURE(400)`, `STALE_EVENT(400)`, `EVENT_ID_REUSED(409)`, `IDEMPOTENCY_CONFLICT(422)`, `REFUND_BLOCKED(409)`, `ALREADY_USED(409)`, `TERM_CLOSED(409)`, `CLOSE_BLOCKED(409)`, `SELF_APPROVAL(403)`, `UPLOAD_REJECTED(422)`, `RATE_LIMITED(429)`.

## 10. Semester close, snapshot, handover (Owner C)

`close.service.run_close(conn, term_id, actor_id) -> SnapshotId` runs inside the caller's single `BEGIN IMMEDIATE` transaction. **The checks, snapshot, term transition, and next-term creation are atomic: all commit or none do.**

Checklist (all must pass or `CLOSE_BLOCKED` with the failing checks returned; no writes):
1. No `payments` in `CREATED`/`PENDING`; none `SUCCEEDED` with `fulfillment='UNFULFILLED'`; no `payment_events` with `outcome='UNAPPLIED_RECEIPT'` and `resolution IS NULL`.
2. No expenses in `SUBMITTED`/`APPROVED`.
3. No live `HELD` ticket holds and no `RESERVED` merch orders.
4. All journal entries for the term are `POSTED` (no `DRAFT`); each balances.
5. **Cumulative** balances as of the close instant: 2100 Reimbursements Payable = 0 and 2000 Unfulfilled Obligation = 0.
6. **Cumulative** 1100 Clearing balance = 0 (all received money settled — run `settle` first).
7. Every `PAID` expense has ≥ 1 receipt.
8. Close instant > `starts_at` of the term. (Early close is allowed; it does not require the academic year to have ended and does not affect memberships, §1.3.)

Then, in the same transaction:
1. Build `totals_json` from §11 (opening balance, period movement, closing balance for every account; income and expense by account; per-event and per-source summaries; counts). `content_sha256 = sha256(canonical JSON)`. Insert `close_snapshots` (triggers forbid UPDATE/DELETE) and `close_checks`.
2. Set the term `CLOSED`, `closed_at = ends_at = now`.
3. Insert the next term `OPEN` with `starts_at = (closed term).ends_at` exactly (no gap, no overlap).
4. Memberships are untouched.

**After close:**
- Journal entries are inserted only into the OPEN term (trigger). Closed-term journal data never changes.
- New purchases (including those for events/products created in an earlier term) get the new term's `term_id` and post to it. Late callbacks for payments created in the closed term follow §3.1 and post to the OPEN term with a prior-term memo.
- **Corrections are adjusting entries in the OPEN term** (`source_type='adjustment'`, `term_id` = OPEN, `adjusts_term_id` = the closed term being corrected, memo required, permission `close.run`). They appear in the OPEN term's movements and in an "Adjustments to prior terms" section of reports. The snapshot is never modified.

**Officer handover:** `handover.service.run_handover(conn, term_id, from_user_id, to_user_id, role_codes, notes)`; precondition: term is `CLOSED` with a snapshot, and no handover exists for it. In one transaction: revoke roles from `from_user` (`revoked_at`), grant to `to_user`, revoke `from_user`'s sessions, write `officer_handover` with `role_changes_json`, audit-log. Requires `handover.run`. At least one other active admin must remain (else `VALIDATION`).

## 11. Reports (Owner C)

Two distinct measures, never mixed:

- **Balance as of a cutoff** (cumulative, for balance-sheet accounts 1000, 1100, 2000, 2100): `balance(account, cutoff) = Σ over all POSTED lines of that account in entries with entry_date < cutoff, across all terms`. Assets: Σdebit − Σcredit. Liabilities: Σcredit − Σdebit. Default cutoff = now. **Cash on hand is always a cumulative balance**, so it does not reset when a term rolls over. Equivalently, a term's opening balance is the previous snapshot's closing balance (a test asserts closing(N) == opening(N+1) for every balance account).
- **Period movement** (for a term): `movement(account, term_id) = Σdebit and Σcredit of POSTED lines in entries with that term_id` (not netted across terms). Income and expense reports use movement of 4xxx/5xxx for the chosen term; "net surplus for the term" = Σ income movement − Σ expense movement. A cumulative net across terms = the sum of terms' nets; it is shown separately, not as cash.

Reports:
- **Cash summary** (default now, optional `?as_of=`): cash on hand = balance(1000), in clearing = balance(1100), unfulfilled obligations = balance(2000), reimbursements payable = balance(2100); plus this term's movements.
- **Income/expense**: by account for a term, plus "Adjustments to prior terms" block.
- **Drill-down**: balance or movement → account → journal entry → source document (payment, event, expense, order, ticket) with links; each level's sums equal the parent's.
- **Event report** (spans all terms, with a per-term split): `sold = count(tickets WHERE status IN ('ISSUED','USED'))`; `attended = count(USED)`; `no_shows = sold − attended`; `gross = Σ tickets.price_paise over status IN ('ISSUED','USED','REFUNDED')`; `refunded = Σ price over REFUNDED`; `net_proceeds = gross − refunded`. **Never join `payments` to `tickets` to sum `payments.amount_paise`** (a multi-ticket payment would be counted once per ticket). All money for an event comes from ticket prices.
- **Journal reconciliation of events**: for each ticket payment P with tickets T(P): `net journal credit to 4100 for source (payment, P)` (credits − debits across its `received`, `fulfilled_late` and reversal entries) must equal `Σ T(P).price_paise over status IN ('ISSUED','USED')`. The query aggregates journal and tickets **separately per payment** and compares the two scalar results; it never joins one to the other. Event net proceeds also equal Σ of those per-payment journal nets for the event's payments (obligation not yet fulfilled sits in 2000, not 4100, and is excluded from both sides).
- **Integrity page/CLI** (`/finance/integrity`, `check-integrity`): total posted debits = total credits; every `SUCCEEDED` payment has exactly one `received` entry; every `PAID` expense has `approved` and `paid` entries; event reconciliation above; each `UNAPPLIED_RECEIPT` with INR amount has a `received` entry; `reserved_qty` of every variant equals the quantity in `RESERVED`/`PAID` orders.

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
| POST `/join` | auth, CSRF, idempotency key | creates `PENDING` membership + payment; redirect `/pay/{public_id}` |
| GET `/members/card` | auth, own | member code + QR |
| GET `/verify` (+ POST `/verify/lookup`) | perm:members.verify | by `member_code` or scanned `qr_token`; shows ACTIVE/EXPIRED + name only |
| GET `/admin/members` | perm:members.manage | list, expiring soon |

### Payments (A)
| GET `/pay/{public_id}` | auth, own | simulator page |
| POST `/pay/{public_id}/outcome` | auth, own, CSRF | server signs and dispatches |
| POST `/webhooks/payments` | signature only | **CSRF-exempt** |
| GET `/admin/payments` | perm:payments.admin | filters: problem, unfulfilled, unapplied receipts |
| POST `/admin/payments/{id}/refund`, `/admin/payments/{id}/fulfill` | perm:payments.admin, CSRF | `resolve_unfulfilled` / `refund_payment` |
| POST `/admin/payment-events/{id}/resolve` | perm:payments.admin, CSRF | `action = REFUND | DISMISS`, note |

### Events (B)
| GET `/events`, `/events/{id}` | public | shows member + public price, seats left |
| POST `/events/{id}/hold` | auth, CSRF, idempotency key | qty; creates hold + payment (or issues free tickets); redirect `/pay/…` |
| GET `/tickets/{id}` | auth, own | QR |
| GET/POST `/admin/events…` | perm:events.manage | create/edit/open/close/cancel |
| GET `/checkin/{event_id}`, POST `/checkin/{event_id}/scan` | perm:events.checkin | `code` (QR text or manual entry) |
| GET `/admin/events/{id}/report` | perm:events.manage or perm:finance.view | |

### Store (B)
| GET `/store`, `/store/{product_id}` | public | shows *available* quantity per size |
| POST `/store/reserve` | auth, CSRF, idempotency key | cart = list of `(variant_id, qty)`; all-or-nothing |
| POST `/store/orders/{id}/cancel` | auth, own, CSRF | |
| GET `/me/orders` | auth, own | |
| GET/POST `/admin/store…` | perm:store.manage | products, variants, restock/adjust `physical_qty` |
| POST `/admin/orders/{id}/pickup` | perm:store.fulfill, CSRF | |

### Comms / tasks (C)
| GET `/`, `/announcements`, `/announcements/{id}` | public | |
| POST `/subscribe`, GET/POST `/unsubscribe/{token}` | public (pre-session CSRF) | one-click via token |
| GET/POST `/admin/announcements…` | perm:comms.publish | create, publish |
| GET `/dev/mail`, `/dev/mail/{id}` | dev/test env only + perm:comms.mail_viewer | captured mail and suppressed rows (§4.4) |
| GET/POST `/admin/fundraisers…`, `/admin/tasks…` | perm:tasks.manage | board view: tasks by status, overdue count |
| PATCH `/tasks/{id}/status` | auth + (owner of task or perm:tasks.manage), CSRF | |

### Expenses / finance (C)
| GET/POST `/expenses/new`, GET `/expenses` | auth | members may submit; list own |
| POST `/expenses/{id}/receipt` | auth, own | upload ≤5 MB, mime allow-list, magic-byte sniff |
| GET `/receipts/{id}` | owner or perm:receipts.view_all | streamed; `Content-Disposition: attachment`, `nosniff`, never under `/static` |
| POST `/admin/expenses/{id}/approve|reject|pay` | perm:expenses.approve / expenses.pay | approver ≠ submitter |
| GET `/finance`, `/finance/accounts/{code}`, `/finance/entries/{id}`, `/finance/integrity` | perm:finance.view | |
| POST `/admin/adjustments` | perm:close.run | adjusting entry (§10) |
| GET/POST `/admin/close` | perm:close.run | checklist view + run |
| GET/POST `/admin/handover` | perm:handover.run | |

## 13. Shared types, service signatures, wiring, transaction ownership

All in the `clubledger/` package. **Services receive `conn: sqlite3.Connection` and never open/commit a transaction.** Routes and CLI commands use `with unit_of_work(db_path) as conn:` (`core/db.py`, Owner A), which issues `BEGIN IMMEDIATE`, commits on normal exit, rolls back on exception.

### 13.1 Shared types (`core/types.py`, Owner A; frozen at H2; changes need A + D agreement)
```python
@dataclass(frozen=True) class Payment: id, public_id, user_id, purpose, ref_table, ref_id, amount_paise, status, fulfillment, term_id
@dataclass(frozen=True) class FulfillResult:
    outcome: Literal["FULFILLED", "UNFULFILLABLE"]
    reason: str | None = None          # required when UNFULFILLABLE: 'TARGET_NOT_LIVE','SOLD_OUT','INSUFFICIENT_STOCK','ALREADY_MEMBER'
@dataclass(frozen=True) class EventOutcome: event_row_id, outcome, reason, payment_id | None, http_status
@dataclass(frozen=True) class Line: account_code: str; debit_paise: int = 0; credit_paise: int = 0
class Fulfiller(Protocol): def __call__(self, conn, payment: Payment, *, manual: bool, now: str) -> FulfillResult
class RefundCheck(Protocol): def __call__(self, conn, payment: Payment) -> None      # raises DomainError REFUND_BLOCKED
class RefundApply(Protocol): def __call__(self, conn, payment: Payment, now: str) -> None
@dataclass(frozen=True) class PurposeHandler: purpose: str; fulfill: Fulfiller; check_refundable: RefundCheck; apply_refund: RefundApply
Handlers = Mapping[str, PurposeHandler]       # keys 'DUES','TICKET','MERCH'
```
Journal posting is **not** a purpose-handler concern: `payments.service` calls the journal itself after the handler returns, using `FulfillResult.outcome` to pick the credit account.

### 13.2 Explicit handler registration (no import side effects)
`clubledger/wiring.py` (Owner A) is the **only** module that imports membership, events, store, payments, journal, reports, etc. together. It exposes `build_handlers() -> Handlers` that constructs the three `PurposeHandler`s from `membership.service`, `events.service`, `store.service`, and `build_services() -> Services` (a dataclass of handlers + clock + config). `main.py`, `cli.py`, and the test fixtures call `build_services()` explicitly and pass `Services`/`Handlers` into `payments.service` functions as an argument (`handlers=`). Import direction: `core` ← `journal` ← `payments` ← (nothing); `core` ← `membership`/`events`/`store` (they import `payments.service.create_payment` and `core`, never `wiring`); `wiring` → everything. `payments` never imports B's modules. No module registers anything at import time (static test greps for module-level mutation of registries).

### 13.3 Signatures
```python
# core/db.py (A)
def connect(path: str) -> sqlite3.Connection
@contextmanager
def unit_of_work(path: str) -> Iterator[sqlite3.Connection]

# core/auth.py (A)
def create_session(conn, user_id: int) -> tuple[str, str]            # (raw_token, csrf_token)
def load_session(conn, raw_token: str) -> Session | None             # validates both expiries, resolves live permissions, slides idle expiry
def revoke_session(conn, session_id: int) -> None
def require_perm(code: str) -> Depends                               # reads DB each call
def verify_csrf(session, supplied: str) -> None

# core/clock.py (A)
def now() -> str; def set_now(dt) -> None; def reset() -> None
def academic_year_bounds(instant: str) -> tuple[str, str, str]       # (label, starts_at_utc, expires_at_utc), Asia/Kolkata

# core/pricing.py (A)
def active_membership(conn, user_id: int, at: str) -> Membership | None
def ticket_price(conn, event_id: int, user_id: int, at: str) -> tuple[int, Literal["MEMBER","PUBLIC"]]
def merch_price(conn, base_paise: int, user_id: int, at: str) -> tuple[int, Literal["MEMBER","PUBLIC"]]

# payments/service.py (A)
def create_payment(conn, *, user_id, purpose, ref_table, ref_id, amount_paise) -> Payment
def handle_event(conn, handlers: Handlers, raw_body: bytes, signature_header: str, now: str) -> EventOutcome   # trusted phase only; §5 step 1 happens in the route/webhook layer
def refund_payment(conn, handlers: Handlers, payment_id: int, actor_id: int) -> None
def resolve_unfulfilled(conn, handlers: Handlers, payment_id: int, action: Literal["REFUND","FULFILL"], actor_id: int) -> None
def resolve_receipt(conn, event_row_id: int, action: Literal["REFUND","DISMISS"], actor_id: int, note: str) -> None
def settle_payments(conn, as_of: str) -> int
def expire_payments(conn, as_of: str) -> int

# membership/service.py (B)
def start_join(conn, user_id, plan_id, idempotency_key) -> Payment
def fulfill_dues(conn, payment, *, manual, now) -> FulfillResult       # PENDING->ACTIVE, member_code, qr_token
def check_refundable_dues(conn, payment) -> None
def apply_refund_dues(conn, payment, now) -> None                      # ACTIVE -> REVOKED
def lookup_member(conn, *, code=None, qr_token=None, at: str) -> MemberCheck
def enqueue_renewal_reminders(conn, as_of: str) -> int                 # enqueue only; also marks lapsed memberships EXPIRED

# events/service.py (B)
def create_hold(conn, user_id, event_id, qty, idempotency_key) -> tuple[TicketHold, Payment | None]   # None for free tickets
def fulfill_ticket_hold(conn, payment, *, manual, now) -> FulfillResult   # HELD(->EXPIRED if manual)->CONSUMED + N tickets (seat_index 1..N), exactly once
def check_refundable_tickets(conn, payment) -> None
def apply_refund_tickets(conn, payment, now) -> None
def expire_holds(conn, as_of: str) -> int
def check_in(conn, event_id, code: str, staff_id: int) -> CheckInResult
def cancel_event(conn, handlers, event_id, actor_id) -> CancelSummary
def event_report(conn, event_id) -> EventReport

# store/service.py (B)
def reserve_cart(conn, user_id, items: list[CartItem], idempotency_key) -> tuple[MerchOrder, Payment]   # all or nothing
def fulfill_merch_order(conn, payment, *, manual, now) -> FulfillResult
def check_refundable_merch(conn, payment) -> None
def apply_refund_merch(conn, payment, now) -> None
def expire_orders(conn, as_of: str) -> int
def mark_picked_up(conn, order_id, staff_id) -> None

# journal/service.py (C) -- called by payments/expenses/close on the SAME conn
def post_entry(conn, *, term_id, entry_date, source_type, source_id, source_event, memo, lines: list[Line],
               reverses_entry_id: int | None = None, adjusts_term_id: int | None = None) -> int   # idempotent; DRAFT -> lines -> POSTED
def reverse_entry(conn, entry_id: int, memo: str) -> int
def reverse_all_for_source(conn, source_type: str, source_id: int, memo: str) -> list[int]   # newest first
def post_payment_received(conn, payment, *, fulfilled: bool) -> int
def post_payment_late_fulfilled(conn, payment) -> int
def post_receipt_event(conn, event_row) -> int | None
def post_settlement(conn, source_type: str, source_id: int, amount_paise: int) -> int
def post_expense_approved(conn, expense) -> int
def post_expense_paid(conn, expense) -> int

# reports/service.py (C)
def balance_as_of(conn, account_code: str, cutoff: str) -> int
def movement(conn, account_code: str, term_id: int) -> Movement        # debit_paise, credit_paise
def cash_summary(conn, as_of: str, term_id: int) -> CashSummary
def income_expense(conn, term_id: int) -> IncomeExpense
def drilldown(conn, *, account_code=None, entry_id=None, term_id=None, as_of=None) -> DrillDown

# comms (C)
def publish_announcement(conn, announcement_id, actor_id) -> int       # enqueues mail
def subscribe(conn, email, user_id=None) -> Subscriber
def unsubscribe(conn, token) -> None
def process_mail_outbox(conn, limit: int = 100) -> int                 # §14

# close/service.py, handover/service.py (C) -- §10
def run_close(conn, term_id, actor_id) -> int
def post_adjustment(conn, actor_id, adjusts_term_id, memo, lines) -> int
def run_handover(conn, term_id, from_user_id, to_user_id, role_codes, notes) -> int
```

**Payment-success transaction (single, owned by the webhook/simulator route):**
```
with unit_of_work() as conn:
    outcome = payments.service.handle_event(conn, handlers, ...)
      # inside: validate -> update payment -> handler.fulfill(conn, ...) -> journal.post_payment_received(conn, ...) -> insert payment_events row
```
All steps share the same connection. A failing journal post rolls back the fulfillment **and** the `payment_events` row; a retry with the same `event_id` is then processed fresh.

**Hold consumption** releases held capacity exactly once because (a) `HELD→CONSUMED` is a guarded `UPDATE` requiring `rowcount == 1`, (b) the capacity query counts only `HELD`, and (c) tickets are inserted with `UNIQUE(hold_id, seat_index)`.

**Merchandise reservation:** `reserve_cart` validates every line (`qty` 1–10, variant and product active, no duplicate variants), then for each line executes the guarded `reserved_qty` update (§1.5); any `rowcount != 1` raises `INSUFFICIENT_STOCK` and the surrounding transaction rolls back the entire cart.

## 14. CLI commands (`python -m clubledger.cli …`)

Each command opens its own `unit_of_work`, is idempotent, and is safe to run from a scheduler every minute or by hand. `--as-of` follows G9.

| Command | Effect |
|---|---|
| `migrate` | applies `migrations/*.sql` in number order (§1), records checksum in `schema_migrations` |
| `reset-db` | dev/test only: deletes and recreates the SQLite file |
| `seed [--demo]` | roles, permissions, accounts, plans, first term, demo data |
| `expire-holds` | `events.expire_holds` + `store.expire_orders` + `payments.expire_payments`; releases capacity/stock exactly once; cancels `PENDING` memberships whose payment expired |
| `send-reminders` | marks lapsed memberships `EXPIRED`; enqueues `RENEW_30D`, `RENEW_7D`, `EXPIRED` mail with `dedupe_key = reminder:{kind}:{membership_id}`; skips users who already hold a later-year `PENDING`/`ACTIVE` membership |
| `process-mail [--limit N]` | for each `QUEUED` row: **re-checks the condition at processing time** — `ANNOUNCEMENT`: subscriber still `SUBSCRIBED`; reminders: membership still unrenewed/not revoked and user `is_active` — otherwise sets `SUPPRESSED` with `suppressed_reason` and writes no capture. Otherwise inserts `mail_capture` (UNIQUE `outbox_id`) and sets `SENT` in the same transaction, so capture is exactly-once. No SMTP. Errors: `attempts += 1`, `FAILED` after 3 |
| `settle` | simulated payout, posts `settled` entries (payments and unapplied receipts) |
| `check-integrity` | runs the §11 integrity checks; exit code 1 on failure |

## 15. Test and evidence conventions
Marker `req(id, kind)` registered in `pytest.ini` with `--strict-markers`; see REQUIREMENTS.md. Owner D owns `pytest.ini`, `tests/conftest.py`, `tests/factories.py`, and `tests/req_coverage.py`, and records `evidence/` containing actual command outputs, pass/fail counts, and screenshot paths. Scores are never invented; if a check was not run, the evidence file states "not run".
