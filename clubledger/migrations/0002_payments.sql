-- 0002_payments.sql: Payments and payment events schema

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
) STRICT;

CREATE UNIQUE INDEX ux_payments_live_target ON payments(ref_table, ref_id)
  WHERE status IN ('CREATED','PENDING','SUCCEEDED');

CREATE INDEX ix_payments_user ON payments(user_id);
CREATE INDEX ix_payments_status ON payments(status, fulfillment);

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
) STRICT;

CREATE INDEX ix_payment_events_unresolved ON payment_events(outcome, resolution);

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
END;
