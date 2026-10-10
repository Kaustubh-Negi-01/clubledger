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
