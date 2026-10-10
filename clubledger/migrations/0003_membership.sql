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
