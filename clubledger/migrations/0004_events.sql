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
