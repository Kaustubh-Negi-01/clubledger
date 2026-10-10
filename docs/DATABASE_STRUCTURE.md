# ClubLedger local preview database structure

Engine: SQLite. Tables: 35. This is the persistent local preview database; automated tests use separate temporary databases.

Database: `database/runtime/clubledger-preview.db`

Schema only; no record contents or credentials are included. Runtime record counts change as you use the application.

| Table | Columns |
| --- | --- |
| `accounts` | `id` (PK), `code`, `name`, `type`, `created_at` |
| `announcements` | `id` (PK), `author_id`, `term_id`, `title`, `body`, `status`, `published_at`, `created_at` |
| `audit_log` | `id` (PK), `actor_user_id`, `action`, `entity`, `entity_id`, `detail`, `created_at` |
| `close_checks` | `id` (PK), `term_id`, `code`, `passed`, `detail`, `evaluated_at`, `created_at` |
| `close_snapshots` | `id` (PK), `term_id`, `taken_at`, `taken_by`, `watermark_entry_id`, `totals_json`, `content_sha256`, `created_at` |
| `events` | `id` (PK), `term_id`, `title`, `venue`, `starts_at`, `ends_at`, `capacity`, `member_price_paise`, `public_price_paise`, `max_per_order`, `status`, `created_at` |
| `expenses` | `id` (PK), `submitter_id`, `term_id`, `category_account_id`, `amount_paise`, `description`, `event_id`, `fundraiser_id`, `task_id`, `status`, `decided_by`, `decided_at`, `decision_note`, `paid_by`, `paid_at`, `created_at` |
| `fundraisers` | `id` (PK), `term_id`, `title`, `goal_paise`, `status`, `created_at` |
| `idempotency_keys` | `actor_user_id` (PK), `action` (PK), `key` (PK), `request_hash`, `result_ref`, `created_at` |
| `journal_entries` | `id` (PK), `term_id`, `entry_date`, `source_type`, `source_id`, `source_event`, `memo`, `status`, `posted_at`, `reverses_entry_id`, `adjusts_term_id`, `created_at` |
| `journal_lines` | `id` (PK), `entry_id`, `account_id`, `debit_paise`, `credit_paise`, `created_at` |
| `mail_capture` | `id` (PK), `outbox_id`, `to_email`, `subject`, `body`, `captured_at`, `created_at` |
| `mail_outbox` | `id` (PK), `dedupe_key`, `to_email`, `subject`, `body`, `kind`, `ref_table`, `ref_id`, `status`, `suppressed_reason`, `attempts`, `last_error`, `processed_at`, `created_at` |
| `membership_plans` | `id` (PK), `code`, `name`, `dues_paise`, `ticket_discount_bps`, `merch_discount_bps`, `is_active`, `created_at` |
| `memberships` | `id` (PK), `user_id`, `plan_id`, `membership_year`, `status`, `starts_at`, `expires_at`, `member_code`, `qr_token`, `payment_id`, `verified_by`, `verified_at`, `created_at` |
| `merch_order_items` | `id` (PK), `order_id`, `variant_id`, `qty`, `unit_price_paise`, `created_at` |
| `merch_orders` | `id` (PK), `user_id`, `status`, `expires_at`, `total_paise`, `price_tier`, `payment_id`, `picked_up_at`, `picked_up_by`, `created_at` |
| `officer_handover` | `id` (PK), `term_id`, `from_user_id`, `to_user_id`, `notes`, `role_changes_json`, `completed_at`, `created_at` |
| `payment_events` | `id` (PK), `event_id`, `body_sha256`, `raw_body`, `type`, `payment_id`, `claimed_user_id`, `claimed_public_id`, `amount_paise`, `currency`, `outcome`, `reason`, `settled_at`, `resolution`, `resolved_by`, `resolved_at`, `resolution_note`, `created_at` |
| `payments` | `id` (PK), `public_id`, `user_id`, `purpose`, `ref_table`, `ref_id`, `amount_paise`, `currency`, `status`, `fulfillment`, `term_id`, `succeeded_at`, `settled_at`, `refunded_at`, `created_at` |
| `permissions` | `id` (PK), `code`, `created_at` |
| `products` | `id` (PK), `name`, `description`, `base_price_paise`, `is_active`, `created_at` |
| `receipts` | `id` (PK), `uploader_id`, `expense_id`, `stored_name`, `original_name`, `mime`, `size_bytes`, `sha256`, `created_at` |
| `role_permissions` | `role_id` (PK), `permission_id` (PK), `created_at` |
| `roles` | `id` (PK), `code`, `created_at` |
| `schema_migrations` | `number` (PK), `filename`, `checksum`, `applied_at` |
| `sessions` | `id` (PK), `token_hash`, `user_id`, `csrf_token`, `last_seen_at`, `idle_expires_at`, `absolute_expires_at`, `revoked_at`, `created_at` |
| `subscribers` | `id` (PK), `email`, `user_id`, `status`, `unsub_token`, `subscribed_at`, `unsubscribed_at`, `created_at` |
| `tasks` | `id` (PK), `fundraiser_id`, `title`, `owner_user_id`, `due_at`, `status`, `created_at` |
| `terms` | `id` (PK), `label`, `starts_at`, `ends_at`, `status`, `closed_at`, `created_at` |
| `ticket_holds` | `id` (PK), `event_id`, `user_id`, `qty`, `unit_price_paise`, `price_tier`, `status`, `expires_at`, `released_at`, `consumed_at`, `created_at` |
| `tickets` | `id` (PK), `event_id`, `hold_id`, `seat_index`, `user_id`, `payment_id`, `code`, `price_paise`, `price_tier`, `status`, `used_at`, `used_by`, `created_at` |
| `user_roles` | `id` (PK), `user_id`, `role_id`, `granted_at`, `revoked_at`, `created_at` |
| `users` | `id` (PK), `email`, `name`, `password_hash`, `is_active`, `created_at` |
| `variants` | `id` (PK), `product_id`, `sku`, `size`, `physical_qty`, `reserved_qty`, `created_at` |

## accounts

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `code` | `TEXT` | Yes | â€” | `â€”` |
| `name` | `TEXT` | Yes | â€” | `â€”` |
| `type` | `TEXT` | Yes | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

```sql
CREATE TABLE accounts (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('ASSET','LIABILITY','INCOME','EXPENSE')),
  created_at TEXT NOT NULL
) STRICT
```

## announcements

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `author_id` | `INTEGER` | Yes | â€” | `â€”` |
| `term_id` | `INTEGER` | Yes | â€” | `â€”` |
| `title` | `TEXT` | Yes | â€” | `â€”` |
| `body` | `TEXT` | Yes | â€” | `â€”` |
| `status` | `TEXT` | Yes | â€” | `â€”` |
| `published_at` | `TEXT` | No | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `term_id` â†’ `terms.id` (delete: NO ACTION; update: NO ACTION).
- `author_id` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE announcements (
 id INTEGER PRIMARY KEY, author_id INTEGER NOT NULL REFERENCES users(id), term_id INTEGER NOT NULL REFERENCES terms(id),
 title TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('DRAFT','PUBLISHED')),
 published_at TEXT, created_at TEXT NOT NULL, CHECK((status='PUBLISHED')=(published_at IS NOT NULL))
) STRICT
```

## audit_log

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `actor_user_id` | `INTEGER` | No | â€” | `â€”` |
| `action` | `TEXT` | Yes | â€” | `â€”` |
| `entity` | `TEXT` | Yes | â€” | `â€”` |
| `entity_id` | `INTEGER` | No | â€” | `â€”` |
| `detail` | `TEXT` | No | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `actor_user_id` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY,
  actor_user_id INTEGER REFERENCES users(id),
  action TEXT NOT NULL,
  entity TEXT NOT NULL,
  entity_id INTEGER,
  detail TEXT,
  created_at TEXT NOT NULL
) STRICT
```

## close_checks

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `term_id` | `INTEGER` | Yes | â€” | `â€”` |
| `code` | `TEXT` | Yes | â€” | `â€”` |
| `passed` | `INTEGER` | Yes | â€” | `â€”` |
| `detail` | `TEXT` | No | â€” | `â€”` |
| `evaluated_at` | `TEXT` | Yes | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `term_id` â†’ `terms.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE close_checks (
 id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL REFERENCES terms(id), code TEXT NOT NULL,
 passed INTEGER NOT NULL CHECK(passed IN (0,1)), detail TEXT, evaluated_at TEXT NOT NULL, created_at TEXT NOT NULL
) STRICT
```

## close_snapshots

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `term_id` | `INTEGER` | Yes | â€” | `â€”` |
| `taken_at` | `TEXT` | Yes | â€” | `â€”` |
| `taken_by` | `INTEGER` | Yes | â€” | `â€”` |
| `watermark_entry_id` | `INTEGER` | Yes | â€” | `â€”` |
| `totals_json` | `TEXT` | Yes | â€” | `â€”` |
| `content_sha256` | `TEXT` | Yes | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `taken_by` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).
- `term_id` â†’ `terms.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE close_snapshots (
 id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL UNIQUE REFERENCES terms(id), taken_at TEXT NOT NULL,
 taken_by INTEGER NOT NULL REFERENCES users(id), watermark_entry_id INTEGER NOT NULL,
 totals_json TEXT NOT NULL, content_sha256 TEXT NOT NULL, created_at TEXT NOT NULL
) STRICT
```

## events

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `term_id` | `INTEGER` | Yes | â€” | `â€”` |
| `title` | `TEXT` | Yes | â€” | `â€”` |
| `venue` | `TEXT` | Yes | â€” | `â€”` |
| `starts_at` | `TEXT` | Yes | â€” | `â€”` |
| `ends_at` | `TEXT` | Yes | â€” | `â€”` |
| `capacity` | `INTEGER` | Yes | â€” | `â€”` |
| `member_price_paise` | `INTEGER` | Yes | â€” | `â€”` |
| `public_price_paise` | `INTEGER` | Yes | â€” | `â€”` |
| `max_per_order` | `INTEGER` | Yes | â€” | `4` |
| `status` | `TEXT` | Yes | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `term_id` â†’ `terms.id` (delete: NO ACTION; update: NO ACTION).

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
) STRICT
```

## expenses

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `submitter_id` | `INTEGER` | Yes | â€” | `â€”` |
| `term_id` | `INTEGER` | Yes | â€” | `â€”` |
| `category_account_id` | `INTEGER` | Yes | â€” | `â€”` |
| `amount_paise` | `INTEGER` | Yes | â€” | `â€”` |
| `description` | `TEXT` | Yes | â€” | `â€”` |
| `event_id` | `INTEGER` | No | â€” | `â€”` |
| `fundraiser_id` | `INTEGER` | No | â€” | `â€”` |
| `task_id` | `INTEGER` | No | â€” | `â€”` |
| `status` | `TEXT` | Yes | â€” | `â€”` |
| `decided_by` | `INTEGER` | No | â€” | `â€”` |
| `decided_at` | `TEXT` | No | â€” | `â€”` |
| `decision_note` | `TEXT` | No | â€” | `â€”` |
| `paid_by` | `INTEGER` | No | â€” | `â€”` |
| `paid_at` | `TEXT` | No | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `task_id` â†’ `tasks.id` (delete: NO ACTION; update: NO ACTION).
- `fundraiser_id` â†’ `tasks.fundraiser_id` (delete: NO ACTION; update: NO ACTION).
- `paid_by` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).
- `decided_by` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).
- `fundraiser_id` â†’ `fundraisers.id` (delete: NO ACTION; update: NO ACTION).
- `event_id` â†’ `events.id` (delete: NO ACTION; update: NO ACTION).
- `category_account_id` â†’ `accounts.id` (delete: NO ACTION; update: NO ACTION).
- `term_id` â†’ `terms.id` (delete: NO ACTION; update: NO ACTION).
- `submitter_id` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE expenses (
  id INTEGER PRIMARY KEY,
  submitter_id INTEGER NOT NULL REFERENCES users(id),
  term_id INTEGER NOT NULL REFERENCES terms(id),
  category_account_id INTEGER NOT NULL REFERENCES accounts(id),
  amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
  description TEXT NOT NULL,
  event_id INTEGER REFERENCES events(id),
  fundraiser_id INTEGER REFERENCES fundraisers(id),
  task_id INTEGER,
  status TEXT NOT NULL CHECK (status IN ('SUBMITTED','APPROVED','REJECTED','PAID','VOID')),
  decided_by INTEGER REFERENCES users(id),
  decided_at TEXT,
  decision_note TEXT,
  paid_by INTEGER REFERENCES users(id),
  paid_at TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (task_id, fundraiser_id) REFERENCES tasks(id, fundraiser_id),
  CHECK (task_id IS NULL OR fundraiser_id IS NOT NULL)
) STRICT
```

## fundraisers

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `term_id` | `INTEGER` | Yes | â€” | `â€”` |
| `title` | `TEXT` | Yes | â€” | `â€”` |
| `goal_paise` | `INTEGER` | No | â€” | `â€”` |
| `status` | `TEXT` | Yes | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `term_id` â†’ `terms.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE fundraisers (
  id INTEGER PRIMARY KEY,
  term_id INTEGER NOT NULL REFERENCES terms(id),
  title TEXT NOT NULL,
  goal_paise INTEGER CHECK (goal_paise IS NULL OR goal_paise > 0),
  status TEXT NOT NULL CHECK (status IN ('PLANNING','ACTIVE','DONE','CANCELLED')),
  created_at TEXT NOT NULL
) STRICT
```

## idempotency_keys

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `actor_user_id` | `INTEGER` | Yes | 1 | `â€”` |
| `action` | `TEXT` | Yes | 2 | `â€”` |
| `key` | `TEXT` | Yes | 3 | `â€”` |
| `request_hash` | `TEXT` | Yes | â€” | `â€”` |
| `result_ref` | `TEXT` | Yes | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `actor_user_id` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE idempotency_keys (
  actor_user_id INTEGER NOT NULL REFERENCES users(id),
  action TEXT NOT NULL,
  key TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  result_ref TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (actor_user_id, action, key)
) STRICT
```

## journal_entries

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `term_id` | `INTEGER` | Yes | â€” | `â€”` |
| `entry_date` | `TEXT` | Yes | â€” | `â€”` |
| `source_type` | `TEXT` | Yes | â€” | `â€”` |
| `source_id` | `INTEGER` | Yes | â€” | `â€”` |
| `source_event` | `TEXT` | Yes | â€” | `â€”` |
| `memo` | `TEXT` | No | â€” | `â€”` |
| `status` | `TEXT` | Yes | â€” | `â€”` |
| `posted_at` | `TEXT` | No | â€” | `â€”` |
| `reverses_entry_id` | `INTEGER` | No | â€” | `â€”` |
| `adjusts_term_id` | `INTEGER` | No | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `adjusts_term_id` â†’ `terms.id` (delete: NO ACTION; update: NO ACTION).
- `reverses_entry_id` â†’ `journal_entries.id` (delete: NO ACTION; update: NO ACTION).
- `term_id` â†’ `terms.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE journal_entries (
  id INTEGER PRIMARY KEY,
  term_id INTEGER NOT NULL REFERENCES terms(id),
  entry_date TEXT NOT NULL,
  source_type TEXT NOT NULL CHECK (source_type IN ('payment','payment_event','expense','adjustment')),
  source_id INTEGER NOT NULL,
  source_event TEXT NOT NULL,
  memo TEXT,
  status TEXT NOT NULL CHECK (status IN ('DRAFT','POSTED')),
  posted_at TEXT,
  reverses_entry_id INTEGER REFERENCES journal_entries(id),
  adjusts_term_id INTEGER REFERENCES terms(id),
  created_at TEXT NOT NULL,
  UNIQUE (source_type, source_id, source_event),
  CHECK ((status = 'POSTED') = (posted_at IS NOT NULL)),
  CHECK (adjusts_term_id IS NULL OR adjusts_term_id <> term_id),
  CHECK (adjusts_term_id IS NULL OR source_type = 'adjustment'),
  CHECK (source_event NOT LIKE '%_reversal' OR reverses_entry_id IS NOT NULL)
) STRICT
```

## journal_lines

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `entry_id` | `INTEGER` | Yes | â€” | `â€”` |
| `account_id` | `INTEGER` | Yes | â€” | `â€”` |
| `debit_paise` | `INTEGER` | Yes | â€” | `0` |
| `credit_paise` | `INTEGER` | Yes | â€” | `0` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `account_id` â†’ `accounts.id` (delete: NO ACTION; update: NO ACTION).
- `entry_id` â†’ `journal_entries.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE journal_lines (
  id INTEGER PRIMARY KEY,
  entry_id INTEGER NOT NULL REFERENCES journal_entries(id),
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  debit_paise INTEGER NOT NULL DEFAULT 0 CHECK (debit_paise >= 0),
  credit_paise INTEGER NOT NULL DEFAULT 0 CHECK (credit_paise >= 0),
  created_at TEXT NOT NULL,
  CHECK ((debit_paise = 0) <> (credit_paise = 0))
) STRICT
```

## mail_capture

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `outbox_id` | `INTEGER` | Yes | â€” | `â€”` |
| `to_email` | `TEXT` | Yes | â€” | `â€”` |
| `subject` | `TEXT` | Yes | â€” | `â€”` |
| `body` | `TEXT` | Yes | â€” | `â€”` |
| `captured_at` | `TEXT` | Yes | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `outbox_id` â†’ `mail_outbox.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE mail_capture (
 id INTEGER PRIMARY KEY, outbox_id INTEGER NOT NULL UNIQUE REFERENCES mail_outbox(id), to_email TEXT NOT NULL,
 subject TEXT NOT NULL, body TEXT NOT NULL, captured_at TEXT NOT NULL, created_at TEXT NOT NULL
) STRICT
```

## mail_outbox

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `dedupe_key` | `TEXT` | Yes | â€” | `â€”` |
| `to_email` | `TEXT` | Yes | â€” | `â€”` |
| `subject` | `TEXT` | Yes | â€” | `â€”` |
| `body` | `TEXT` | Yes | â€” | `â€”` |
| `kind` | `TEXT` | Yes | â€” | `â€”` |
| `ref_table` | `TEXT` | Yes | â€” | `â€”` |
| `ref_id` | `INTEGER` | Yes | â€” | `â€”` |
| `status` | `TEXT` | Yes | â€” | `â€”` |
| `suppressed_reason` | `TEXT` | No | â€” | `â€”` |
| `attempts` | `INTEGER` | Yes | â€” | `0` |
| `last_error` | `TEXT` | No | â€” | `â€”` |
| `processed_at` | `TEXT` | No | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

```sql
CREATE TABLE mail_outbox (
 id INTEGER PRIMARY KEY, dedupe_key TEXT NOT NULL UNIQUE, to_email TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('ANNOUNCEMENT','RENEW_30D','RENEW_7D','EXPIRED')),
 ref_table TEXT NOT NULL CHECK(ref_table IN ('announcements','memberships')), ref_id INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('QUEUED','SENT','FAILED','SUPPRESSED')), suppressed_reason TEXT,
 attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, processed_at TEXT, created_at TEXT NOT NULL,
 CHECK((status='SUPPRESSED')=(suppressed_reason IS NOT NULL))
) STRICT
```

## membership_plans

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `code` | `TEXT` | Yes | â€” | `â€”` |
| `name` | `TEXT` | Yes | â€” | `â€”` |
| `dues_paise` | `INTEGER` | Yes | â€” | `â€”` |
| `ticket_discount_bps` | `INTEGER` | Yes | â€” | `â€”` |
| `merch_discount_bps` | `INTEGER` | Yes | â€” | `â€”` |
| `is_active` | `INTEGER` | Yes | â€” | `1` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

```sql
CREATE TABLE membership_plans (
  id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  dues_paise INTEGER NOT NULL CHECK (dues_paise > 0),
  ticket_discount_bps INTEGER NOT NULL CHECK (ticket_discount_bps BETWEEN 0 AND 10000),
  merch_discount_bps  INTEGER NOT NULL CHECK (merch_discount_bps  BETWEEN 0 AND 10000),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  created_at TEXT NOT NULL
) STRICT
```

## memberships

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `user_id` | `INTEGER` | Yes | â€” | `â€”` |
| `plan_id` | `INTEGER` | Yes | â€” | `â€”` |
| `membership_year` | `TEXT` | Yes | â€” | `â€”` |
| `status` | `TEXT` | Yes | â€” | `â€”` |
| `starts_at` | `TEXT` | Yes | â€” | `â€”` |
| `expires_at` | `TEXT` | Yes | â€” | `â€”` |
| `member_code` | `TEXT` | No | â€” | `â€”` |
| `qr_token` | `TEXT` | No | â€” | `â€”` |
| `payment_id` | `INTEGER` | No | â€” | `â€”` |
| `verified_by` | `INTEGER` | No | â€” | `â€”` |
| `verified_at` | `TEXT` | No | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `verified_by` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).
- `payment_id` â†’ `payments.id` (delete: NO ACTION; update: NO ACTION).
- `plan_id` â†’ `membership_plans.id` (delete: NO ACTION; update: NO ACTION).
- `user_id` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).

```sql
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
) STRICT
```

## merch_order_items

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `order_id` | `INTEGER` | Yes | â€” | `â€”` |
| `variant_id` | `INTEGER` | Yes | â€” | `â€”` |
| `qty` | `INTEGER` | Yes | â€” | `â€”` |
| `unit_price_paise` | `INTEGER` | Yes | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `variant_id` â†’ `variants.id` (delete: NO ACTION; update: NO ACTION).
- `order_id` â†’ `merch_orders.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE merch_order_items (
  id INTEGER PRIMARY KEY,
  order_id INTEGER NOT NULL REFERENCES merch_orders(id),
  variant_id INTEGER NOT NULL REFERENCES variants(id),
  qty INTEGER NOT NULL CHECK (qty BETWEEN 1 AND 10),
  unit_price_paise INTEGER NOT NULL CHECK (unit_price_paise > 0),
  created_at TEXT NOT NULL,
  UNIQUE (order_id, variant_id)
) STRICT
```

## merch_orders

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `user_id` | `INTEGER` | Yes | â€” | `â€”` |
| `status` | `TEXT` | Yes | â€” | `â€”` |
| `expires_at` | `TEXT` | Yes | â€” | `â€”` |
| `total_paise` | `INTEGER` | Yes | â€” | `â€”` |
| `price_tier` | `TEXT` | Yes | â€” | `â€”` |
| `payment_id` | `INTEGER` | No | â€” | `â€”` |
| `picked_up_at` | `TEXT` | No | â€” | `â€”` |
| `picked_up_by` | `INTEGER` | No | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `picked_up_by` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).
- `payment_id` â†’ `payments.id` (delete: NO ACTION; update: NO ACTION).
- `user_id` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE merch_orders (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  status TEXT NOT NULL CHECK (status IN ('RESERVED','PAID','PICKED_UP','CANCELLED','EXPIRED','REFUNDED')),
  expires_at TEXT NOT NULL, total_paise INTEGER NOT NULL CHECK (total_paise >= 0),
  price_tier TEXT NOT NULL CHECK (price_tier IN ('MEMBER','PUBLIC')),
  payment_id INTEGER REFERENCES payments(id),
  picked_up_at TEXT, picked_up_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
) STRICT
```

## officer_handover

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `term_id` | `INTEGER` | Yes | â€” | `â€”` |
| `from_user_id` | `INTEGER` | Yes | â€” | `â€”` |
| `to_user_id` | `INTEGER` | Yes | â€” | `â€”` |
| `notes` | `TEXT` | No | â€” | `â€”` |
| `role_changes_json` | `TEXT` | Yes | â€” | `â€”` |
| `completed_at` | `TEXT` | Yes | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `to_user_id` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).
- `from_user_id` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).
- `term_id` â†’ `terms.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE officer_handover (
 id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL UNIQUE REFERENCES terms(id),
 from_user_id INTEGER NOT NULL REFERENCES users(id), to_user_id INTEGER NOT NULL REFERENCES users(id),
 notes TEXT, role_changes_json TEXT NOT NULL, completed_at TEXT NOT NULL, created_at TEXT NOT NULL
) STRICT
```

## payment_events

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `event_id` | `TEXT` | Yes | â€” | `â€”` |
| `body_sha256` | `TEXT` | Yes | â€” | `â€”` |
| `raw_body` | `TEXT` | Yes | â€” | `â€”` |
| `type` | `TEXT` | Yes | â€” | `â€”` |
| `payment_id` | `INTEGER` | No | â€” | `â€”` |
| `claimed_user_id` | `INTEGER` | No | â€” | `â€”` |
| `claimed_public_id` | `TEXT` | Yes | â€” | `â€”` |
| `amount_paise` | `INTEGER` | Yes | â€” | `â€”` |
| `currency` | `TEXT` | Yes | â€” | `â€”` |
| `outcome` | `TEXT` | Yes | â€” | `â€”` |
| `reason` | `TEXT` | No | â€” | `â€”` |
| `settled_at` | `TEXT` | No | â€” | `â€”` |
| `resolution` | `TEXT` | No | â€” | `â€”` |
| `resolved_by` | `INTEGER` | No | â€” | `â€”` |
| `resolved_at` | `TEXT` | No | â€” | `â€”` |
| `resolution_note` | `TEXT` | No | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `resolved_by` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).
- `payment_id` â†’ `payments.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE payment_events (
  id INTEGER PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,
  body_sha256 TEXT NOT NULL,
  raw_body TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('payment.succeeded','payment.failed')),
  payment_id INTEGER REFERENCES payments(id),
  claimed_user_id INTEGER,
  claimed_public_id TEXT NOT NULL,
  amount_paise INTEGER NOT NULL,
  currency TEXT NOT NULL,
  outcome TEXT NOT NULL CHECK (outcome IN ('APPLIED','APPLIED_UNFULFILLED','UNAPPLIED_RECEIPT','NO_EFFECT')),
  reason TEXT,
  settled_at TEXT,
  resolution TEXT CHECK (resolution IN ('REFUNDED','DISMISSED')),
  resolved_by INTEGER REFERENCES users(id),
  resolved_at TEXT,
  resolution_note TEXT,
  created_at TEXT NOT NULL,
  CHECK (outcome = 'UNAPPLIED_RECEIPT' OR resolution IS NULL)
) STRICT
```

## payments

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `public_id` | `TEXT` | Yes | â€” | `â€”` |
| `user_id` | `INTEGER` | Yes | â€” | `â€”` |
| `purpose` | `TEXT` | Yes | â€” | `â€”` |
| `ref_table` | `TEXT` | Yes | â€” | `â€”` |
| `ref_id` | `INTEGER` | Yes | â€” | `â€”` |
| `amount_paise` | `INTEGER` | Yes | â€” | `â€”` |
| `currency` | `TEXT` | Yes | â€” | `'INR'` |
| `status` | `TEXT` | Yes | â€” | `â€”` |
| `fulfillment` | `TEXT` | Yes | â€” | `'NONE'` |
| `term_id` | `INTEGER` | Yes | â€” | `â€”` |
| `succeeded_at` | `TEXT` | No | â€” | `â€”` |
| `settled_at` | `TEXT` | No | â€” | `â€”` |
| `refunded_at` | `TEXT` | No | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `term_id` â†’ `terms.id` (delete: NO ACTION; update: NO ACTION).
- `user_id` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE payments (
  id INTEGER PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,
  user_id INTEGER NOT NULL REFERENCES users(id),
  purpose TEXT NOT NULL CHECK (purpose IN ('DUES','TICKET','MERCH')),
  ref_table TEXT NOT NULL CHECK (ref_table IN ('memberships','ticket_holds','merch_orders')),
  ref_id INTEGER NOT NULL,
  amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
  currency TEXT NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
  status TEXT NOT NULL CHECK (status IN ('CREATED','PENDING','SUCCEEDED','FAILED','EXPIRED','REFUNDED')),
  fulfillment TEXT NOT NULL DEFAULT 'NONE'
    CHECK (fulfillment IN ('NONE','FULFILLED','UNFULFILLED','RESOLVED_REFUNDED')),
  term_id INTEGER NOT NULL REFERENCES terms(id),
  succeeded_at TEXT,
  settled_at TEXT,
  refunded_at TEXT,
  created_at TEXT NOT NULL,
  CHECK (fulfillment <> 'FULFILLED' OR status IN ('SUCCEEDED','REFUNDED')),
  CHECK (fulfillment <> 'UNFULFILLED' OR status = 'SUCCEEDED')
) STRICT
```

## permissions

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `code` | `TEXT` | Yes | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

```sql
CREATE TABLE permissions (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
) STRICT
```

## products

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `name` | `TEXT` | Yes | â€” | `â€”` |
| `description` | `TEXT` | Yes | â€” | `''` |
| `base_price_paise` | `INTEGER` | Yes | â€” | `â€”` |
| `is_active` | `INTEGER` | Yes | â€” | `1` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

```sql
CREATE TABLE products (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
  base_price_paise INTEGER NOT NULL CHECK (base_price_paise > 0),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)), created_at TEXT NOT NULL
) STRICT
```

## receipts

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `uploader_id` | `INTEGER` | Yes | â€” | `â€”` |
| `expense_id` | `INTEGER` | Yes | â€” | `â€”` |
| `stored_name` | `TEXT` | Yes | â€” | `â€”` |
| `original_name` | `TEXT` | Yes | â€” | `â€”` |
| `mime` | `TEXT` | Yes | â€” | `â€”` |
| `size_bytes` | `INTEGER` | Yes | â€” | `â€”` |
| `sha256` | `TEXT` | Yes | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `expense_id` â†’ `expenses.id` (delete: NO ACTION; update: NO ACTION).
- `uploader_id` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE receipts (
  id INTEGER PRIMARY KEY,
  uploader_id INTEGER NOT NULL REFERENCES users(id),
  expense_id INTEGER NOT NULL REFERENCES expenses(id),
  stored_name TEXT NOT NULL UNIQUE,
  original_name TEXT NOT NULL,
  mime TEXT NOT NULL CHECK (mime IN ('image/png','image/jpeg','application/pdf')),
  size_bytes INTEGER NOT NULL CHECK (size_bytes BETWEEN 1 AND 5242880),
  sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL
) STRICT
```

## role_permissions

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `role_id` | `INTEGER` | Yes | 1 | `â€”` |
| `permission_id` | `INTEGER` | Yes | 2 | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `permission_id` â†’ `permissions.id` (delete: NO ACTION; update: NO ACTION).
- `role_id` â†’ `roles.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE role_permissions (
  role_id INTEGER NOT NULL REFERENCES roles(id),
  permission_id INTEGER NOT NULL REFERENCES permissions(id),
  created_at TEXT NOT NULL,
  PRIMARY KEY (role_id, permission_id)
) STRICT
```

## roles

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `code` | `TEXT` | Yes | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

```sql
CREATE TABLE roles (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
) STRICT
```

## schema_migrations

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `number` | `INTEGER` | Yes | 1 | `â€”` |
| `filename` | `TEXT` | Yes | â€” | `â€”` |
| `checksum` | `TEXT` | Yes | â€” | `â€”` |
| `applied_at` | `TEXT` | Yes | â€” | `â€”` |

```sql
CREATE TABLE schema_migrations (
  number INTEGER PRIMARY KEY,
  filename TEXT NOT NULL,
  checksum TEXT NOT NULL,
  applied_at TEXT NOT NULL
) STRICT
```

## sessions

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `token_hash` | `TEXT` | Yes | â€” | `â€”` |
| `user_id` | `INTEGER` | Yes | â€” | `â€”` |
| `csrf_token` | `TEXT` | Yes | â€” | `â€”` |
| `last_seen_at` | `TEXT` | Yes | â€” | `â€”` |
| `idle_expires_at` | `TEXT` | Yes | â€” | `â€”` |
| `absolute_expires_at` | `TEXT` | Yes | â€” | `â€”` |
| `revoked_at` | `TEXT` | No | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `user_id` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE sessions (
  id INTEGER PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  user_id INTEGER NOT NULL REFERENCES users(id),
  csrf_token TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  idle_expires_at TEXT NOT NULL,
  absolute_expires_at TEXT NOT NULL,
  revoked_at TEXT,
  created_at TEXT NOT NULL
) STRICT
```

## subscribers

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `email` | `TEXT` | Yes | â€” | `â€”` |
| `user_id` | `INTEGER` | No | â€” | `â€”` |
| `status` | `TEXT` | Yes | â€” | `â€”` |
| `unsub_token` | `TEXT` | Yes | â€” | `â€”` |
| `subscribed_at` | `TEXT` | Yes | â€” | `â€”` |
| `unsubscribed_at` | `TEXT` | No | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `user_id` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE subscribers (
 id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE, user_id INTEGER REFERENCES users(id),
 status TEXT NOT NULL CHECK(status IN ('SUBSCRIBED','UNSUBSCRIBED')), unsub_token TEXT NOT NULL UNIQUE,
 subscribed_at TEXT NOT NULL, unsubscribed_at TEXT, created_at TEXT NOT NULL
) STRICT
```

## tasks

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `fundraiser_id` | `INTEGER` | Yes | â€” | `â€”` |
| `title` | `TEXT` | Yes | â€” | `â€”` |
| `owner_user_id` | `INTEGER` | No | â€” | `â€”` |
| `due_at` | `TEXT` | No | â€” | `â€”` |
| `status` | `TEXT` | Yes | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `owner_user_id` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).
- `fundraiser_id` â†’ `fundraisers.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE tasks (
  id INTEGER PRIMARY KEY,
  fundraiser_id INTEGER NOT NULL REFERENCES fundraisers(id),
  title TEXT NOT NULL,
  owner_user_id INTEGER REFERENCES users(id),
  due_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('TODO','DOING','DONE','BLOCKED')),
  created_at TEXT NOT NULL,
  UNIQUE (id, fundraiser_id)
) STRICT
```

## terms

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `label` | `TEXT` | Yes | â€” | `â€”` |
| `starts_at` | `TEXT` | Yes | â€” | `â€”` |
| `ends_at` | `TEXT` | No | â€” | `â€”` |
| `status` | `TEXT` | Yes | â€” | `â€”` |
| `closed_at` | `TEXT` | No | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

```sql
CREATE TABLE terms (
  id INTEGER PRIMARY KEY,
  label TEXT NOT NULL UNIQUE,
  starts_at TEXT NOT NULL,
  ends_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('OPEN','CLOSED')),
  closed_at TEXT,
  created_at TEXT NOT NULL,
  CHECK ((status = 'OPEN' AND ends_at IS NULL AND closed_at IS NULL)
      OR (status = 'CLOSED' AND ends_at IS NOT NULL AND closed_at IS NOT NULL AND ends_at > starts_at))
) STRICT
```

## ticket_holds

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `event_id` | `INTEGER` | Yes | â€” | `â€”` |
| `user_id` | `INTEGER` | Yes | â€” | `â€”` |
| `qty` | `INTEGER` | Yes | â€” | `â€”` |
| `unit_price_paise` | `INTEGER` | Yes | â€” | `â€”` |
| `price_tier` | `TEXT` | Yes | â€” | `â€”` |
| `status` | `TEXT` | Yes | â€” | `â€”` |
| `expires_at` | `TEXT` | Yes | â€” | `â€”` |
| `released_at` | `TEXT` | No | â€” | `â€”` |
| `consumed_at` | `TEXT` | No | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `user_id` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).
- `event_id` â†’ `events.id` (delete: NO ACTION; update: NO ACTION).

```sql
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
) STRICT
```

## tickets

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `event_id` | `INTEGER` | Yes | â€” | `â€”` |
| `hold_id` | `INTEGER` | Yes | â€” | `â€”` |
| `seat_index` | `INTEGER` | Yes | â€” | `â€”` |
| `user_id` | `INTEGER` | Yes | â€” | `â€”` |
| `payment_id` | `INTEGER` | No | â€” | `â€”` |
| `code` | `TEXT` | Yes | â€” | `â€”` |
| `price_paise` | `INTEGER` | Yes | â€” | `â€”` |
| `price_tier` | `TEXT` | Yes | â€” | `â€”` |
| `status` | `TEXT` | Yes | â€” | `â€”` |
| `used_at` | `TEXT` | No | â€” | `â€”` |
| `used_by` | `INTEGER` | No | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `used_by` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).
- `payment_id` â†’ `payments.id` (delete: NO ACTION; update: NO ACTION).
- `user_id` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).
- `hold_id` â†’ `ticket_holds.id` (delete: NO ACTION; update: NO ACTION).
- `event_id` â†’ `events.id` (delete: NO ACTION; update: NO ACTION).

```sql
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
) STRICT
```

## user_roles

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `user_id` | `INTEGER` | Yes | â€” | `â€”` |
| `role_id` | `INTEGER` | Yes | â€” | `â€”` |
| `granted_at` | `TEXT` | Yes | â€” | `â€”` |
| `revoked_at` | `TEXT` | No | â€” | `â€”` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `role_id` â†’ `roles.id` (delete: NO ACTION; update: NO ACTION).
- `user_id` â†’ `users.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE user_roles (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  role_id INTEGER NOT NULL REFERENCES roles(id),
  granted_at TEXT NOT NULL,
  revoked_at TEXT,
  created_at TEXT NOT NULL
) STRICT
```

## users

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `email` | `TEXT` | Yes | â€” | `â€”` |
| `name` | `TEXT` | Yes | â€” | `â€”` |
| `password_hash` | `TEXT` | Yes | â€” | `â€”` |
| `is_active` | `INTEGER` | Yes | â€” | `1` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  created_at TEXT NOT NULL
) STRICT
```

## variants

| Column | Type | Required | Primary key | Default |
| --- | --- | --- | --- | --- |
| `id` | `INTEGER` | Yes | 1 | `â€”` |
| `product_id` | `INTEGER` | Yes | â€” | `â€”` |
| `sku` | `TEXT` | Yes | â€” | `â€”` |
| `size` | `TEXT` | Yes | â€” | `â€”` |
| `physical_qty` | `INTEGER` | Yes | â€” | `â€”` |
| `reserved_qty` | `INTEGER` | Yes | â€” | `0` |
| `created_at` | `TEXT` | Yes | â€” | `â€”` |

Foreign keys:
- `product_id` â†’ `products.id` (delete: NO ACTION; update: NO ACTION).

```sql
CREATE TABLE variants (
  id INTEGER PRIMARY KEY,
  product_id INTEGER NOT NULL REFERENCES products(id),
  sku TEXT NOT NULL UNIQUE, size TEXT NOT NULL,
  physical_qty INTEGER NOT NULL CHECK (physical_qty >= 0),   -- units the club physically holds; changes only by staff restock/adjust and by pickup
  reserved_qty INTEGER NOT NULL DEFAULT 0 CHECK (reserved_qty >= 0),   -- units promised to RESERVED or PAID-not-yet-picked-up orders
  created_at TEXT NOT NULL,
  UNIQUE (product_id, size),
  CHECK (reserved_qty <= physical_qty)
) STRICT
```

## Indexes, triggers and views

### index: ix_entries_asof

```sql
CREATE INDEX ix_entries_asof ON journal_entries(status, entry_date)
```

### index: ix_entries_source

```sql
CREATE INDEX ix_entries_source ON journal_entries(source_type, source_id)
```

### index: ix_entries_term

```sql
CREATE INDEX ix_entries_term ON journal_entries(term_id, entry_date)
```

### index: ix_expenses_status

```sql
CREATE INDEX ix_expenses_status ON expenses(status)
```

### index: ix_holds_event

```sql
CREATE INDEX ix_holds_event ON ticket_holds(event_id, status)
```

### index: ix_holds_expiry

```sql
CREATE INDEX ix_holds_expiry ON ticket_holds(status, expires_at)
```

### index: ix_lines_account

```sql
CREATE INDEX ix_lines_account ON journal_lines(account_id)
```

### index: ix_lines_entry

```sql
CREATE INDEX ix_lines_entry ON journal_lines(entry_id)
```

### index: ix_memberships_expiry

```sql
CREATE INDEX ix_memberships_expiry ON memberships(status, expires_at)
```

### index: ix_orders_expiry

```sql
CREATE INDEX ix_orders_expiry ON merch_orders(status, expires_at)
```

### index: ix_orders_user

```sql
CREATE INDEX ix_orders_user ON merch_orders(user_id)
```

### index: ix_outbox_status

```sql
CREATE INDEX ix_outbox_status ON mail_outbox(status)
```

### index: ix_payment_events_unresolved

```sql
CREATE INDEX ix_payment_events_unresolved ON payment_events(outcome, resolution)
```

### index: ix_payments_status

```sql
CREATE INDEX ix_payments_status ON payments(status, fulfillment)
```

### index: ix_payments_user

```sql
CREATE INDEX ix_payments_user ON payments(user_id)
```

### index: ix_receipts_expense

```sql
CREATE INDEX ix_receipts_expense ON receipts(expense_id)
```

### index: ix_sessions_user

```sql
CREATE INDEX ix_sessions_user ON sessions(user_id)
```

### index: ix_tickets_event

```sql
CREATE INDEX ix_tickets_event ON tickets(event_id, status)
```

### index: ix_tickets_payment

```sql
CREATE INDEX ix_tickets_payment ON tickets(payment_id)
```

### index: ix_tickets_user

```sql
CREATE INDEX ix_tickets_user ON tickets(user_id)
```

### index: ux_entries_reversal

```sql
CREATE UNIQUE INDEX ux_entries_reversal ON journal_entries(reverses_entry_id) WHERE reverses_entry_id IS NOT NULL
```

### index: ux_member_user_year

```sql
CREATE UNIQUE INDEX ux_member_user_year ON memberships(user_id, membership_year) WHERE status IN ('PENDING','ACTIVE')
```

### index: ux_payments_live_target

```sql
CREATE UNIQUE INDEX ux_payments_live_target ON payments(ref_table, ref_id)
  WHERE status IN ('CREATED','PENDING','SUCCEEDED')
```

### index: ux_terms_one_open

```sql
CREATE UNIQUE INDEX ux_terms_one_open ON terms(status) WHERE status = 'OPEN'
```

### index: ux_user_roles_live

```sql
CREATE UNIQUE INDEX ux_user_roles_live ON user_roles(user_id, role_id) WHERE revoked_at IS NULL
```

### trigger: immutable_announcements

```sql
CREATE TRIGGER immutable_announcements BEFORE UPDATE ON announcements WHEN OLD.status='PUBLISHED'
BEGIN SELECT RAISE(ABORT,'PUBLISHED_IMMUTABLE'); END
```

### trigger: immutable_snapshot_delete

```sql
CREATE TRIGGER immutable_snapshot_delete BEFORE DELETE ON close_snapshots BEGIN SELECT RAISE(ABORT,'SNAPSHOT_IMMUTABLE'); END
```

### trigger: immutable_snapshot_update

```sql
CREATE TRIGGER immutable_snapshot_update BEFORE UPDATE ON close_snapshots BEGIN SELECT RAISE(ABORT,'SNAPSHOT_IMMUTABLE'); END
```

### trigger: preserve_announcements

```sql
CREATE TRIGGER preserve_announcements BEFORE DELETE ON announcements WHEN OLD.status='PUBLISHED'
BEGIN SELECT RAISE(ABORT,'PUBLISHED_IMMUTABLE'); END
```

### trigger: trg_entry_adjusts_term_check

```sql
CREATE TRIGGER trg_entry_adjusts_term_check
BEFORE UPDATE OF adjusts_term_id ON journal_entries
FOR EACH ROW
WHEN NEW.adjusts_term_id IS NOT NULL
BEGIN
  SELECT CASE
    WHEN (SELECT status FROM terms WHERE id = NEW.adjusts_term_id) <> 'CLOSED' THEN
      RAISE(ABORT, 'adjusts_term_id must reference a CLOSED term')
  END;
END
```

### trigger: trg_entry_immutable_posted_delete

```sql
CREATE TRIGGER trg_entry_immutable_posted_delete
BEFORE DELETE ON journal_entries
FOR EACH ROW
WHEN OLD.status = 'POSTED'
BEGIN
  SELECT RAISE(ABORT, 'POSTED journal entries cannot be deleted');
END
```

### trigger: trg_entry_immutable_posted_update

```sql
CREATE TRIGGER trg_entry_immutable_posted_update
BEFORE UPDATE ON journal_entries
FOR EACH ROW
WHEN OLD.status = 'POSTED'
BEGIN
  SELECT RAISE(ABORT, 'POSTED journal entries are immutable');
END
```

### trigger: trg_entry_insert_draft_only

```sql
CREATE TRIGGER trg_entry_insert_draft_only
BEFORE INSERT ON journal_entries
FOR EACH ROW
BEGIN
  SELECT CASE
    WHEN NEW.status <> 'DRAFT' THEN
      RAISE(ABORT, 'Direct INSERT of POSTED entry is not allowed')
    WHEN (SELECT status FROM terms WHERE id = NEW.term_id) <> 'OPEN' THEN
      RAISE(ABORT, 'TERM_CLOSED')
    WHEN NEW.adjusts_term_id IS NOT NULL AND (SELECT status FROM terms WHERE id = NEW.adjusts_term_id) <> 'CLOSED' THEN
      RAISE(ABORT, 'adjusts_term_id must reference a CLOSED term')
  END;
END
```

### trigger: trg_entry_post_check

```sql
CREATE TRIGGER trg_entry_post_check
BEFORE UPDATE OF status ON journal_entries
FOR EACH ROW
WHEN NEW.status = 'POSTED'
BEGIN
  SELECT CASE
    WHEN OLD.status <> 'DRAFT' THEN
      RAISE(ABORT, 'Only DRAFT entries can be transitioned to POSTED')
    WHEN (SELECT status FROM terms WHERE id = NEW.term_id) <> 'OPEN' THEN
      RAISE(ABORT, 'TERM_CLOSED')
    WHEN NEW.adjusts_term_id IS NOT NULL AND (SELECT status FROM terms WHERE id = NEW.adjusts_term_id) <> 'CLOSED' THEN
      RAISE(ABORT, 'adjusts_term_id must reference a CLOSED term')
    WHEN (SELECT COUNT(*) FROM journal_lines WHERE entry_id = NEW.id) < 2 THEN
      RAISE(ABORT, 'Posted entry must have at least 2 lines')
    WHEN (SELECT COALESCE(SUM(debit_paise), 0) FROM journal_lines WHERE entry_id = NEW.id) <>
         (SELECT COALESCE(SUM(credit_paise), 0) FROM journal_lines WHERE entry_id = NEW.id) THEN
      RAISE(ABORT, 'Debits and credits must balance')
    WHEN (SELECT COALESCE(SUM(debit_paise), 0) FROM journal_lines WHERE entry_id = NEW.id) <= 0 THEN
      RAISE(ABORT, 'Total amount must be greater than zero')
  END;
END
```

### trigger: trg_entry_term_fixed

```sql
CREATE TRIGGER trg_entry_term_fixed
BEFORE UPDATE OF term_id, source_type, source_id, source_event, reverses_entry_id ON journal_entries
FOR EACH ROW
BEGIN
  SELECT RAISE(ABORT, 'Key entry fields cannot be modified');
END
```

### trigger: trg_line_delete_draft_only

```sql
CREATE TRIGGER trg_line_delete_draft_only
BEFORE DELETE ON journal_lines
FOR EACH ROW
BEGIN
  SELECT CASE
    WHEN (SELECT status FROM journal_entries WHERE id = OLD.entry_id) = 'POSTED' THEN
      RAISE(ABORT, 'Cannot delete lines from a POSTED entry')
  END;
END
```

### trigger: trg_line_insert_draft_only

```sql
CREATE TRIGGER trg_line_insert_draft_only
BEFORE INSERT ON journal_lines
FOR EACH ROW
BEGIN
  SELECT CASE
    WHEN (SELECT status FROM journal_entries WHERE id = NEW.entry_id) IS NULL THEN
      RAISE(ABORT, 'Parent journal entry does not exist')
    WHEN (SELECT status FROM journal_entries WHERE id = NEW.entry_id) <> 'DRAFT' THEN
      RAISE(ABORT, 'Lines can only be inserted into DRAFT entries')
  END;
END
```

### trigger: trg_line_update_blocked

```sql
CREATE TRIGGER trg_line_update_blocked
BEFORE UPDATE ON journal_lines
FOR EACH ROW
BEGIN
  SELECT CASE
    WHEN NEW.entry_id <> OLD.entry_id THEN
      RAISE(ABORT, 'entry_id cannot be changed')
    WHEN (SELECT status FROM journal_entries WHERE id = OLD.entry_id) = 'POSTED' THEN
      RAISE(ABORT, 'Cannot update lines of a POSTED entry')
    WHEN (SELECT status FROM journal_entries WHERE id = NEW.entry_id) = 'POSTED' THEN
      RAISE(ABORT, 'Cannot move lines into a POSTED entry')
  END;
END
```

### trigger: trg_payment_events_outcome_immutable

```sql
CREATE TRIGGER trg_payment_events_outcome_immutable
BEFORE UPDATE ON payment_events
BEGIN
  SELECT CASE
    WHEN OLD.outcome <> NEW.outcome THEN
      RAISE(ABORT, 'payment_events.outcome is immutable')
    WHEN OLD.outcome <> 'UNAPPLIED_RECEIPT' AND (
      OLD.settled_at IS NOT NEW.settled_at OR
      OLD.resolution IS NOT NEW.resolution OR
      OLD.resolved_by IS NOT NEW.resolved_by OR
      OLD.resolved_at IS NOT NEW.resolved_at OR
      OLD.resolution_note IS NOT NEW.resolution_note
    ) THEN
      RAISE(ABORT, 'payment_events fields mutable only for UNAPPLIED_RECEIPT')
    WHEN (
      OLD.event_id IS NOT NEW.event_id OR
      OLD.body_sha256 IS NOT NEW.body_sha256 OR
      OLD.raw_body IS NOT NEW.raw_body OR
      OLD.type IS NOT NEW.type OR
      OLD.payment_id IS NOT NEW.payment_id OR
      OLD.claimed_user_id IS NOT NEW.claimed_user_id OR
      OLD.claimed_public_id IS NOT NEW.claimed_public_id OR
      OLD.amount_paise IS NOT NEW.amount_paise OR
      OLD.currency IS NOT NEW.currency OR
      OLD.reason IS NOT NEW.reason OR
      OLD.created_at IS NOT NEW.created_at
    ) THEN
      RAISE(ABORT, 'payment_events fields are immutable')
  END;
END
```
