import sqlite3
from pathlib import Path
import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


def get_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    # Minimal prerequisite mock schema for foreign keys
    conn.executescript("""
    CREATE TABLE users (
      id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
      name TEXT NOT NULL, password_hash TEXT NOT NULL,
      is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
      created_at TEXT NOT NULL
    ) STRICT;
    CREATE TABLE terms (
      id INTEGER PRIMARY KEY, label TEXT NOT NULL UNIQUE, starts_at TEXT NOT NULL,
      ends_at TEXT, status TEXT NOT NULL CHECK (status IN ('OPEN','CLOSED')),
      closed_at TEXT, created_at TEXT NOT NULL
    ) STRICT;
    CREATE TABLE payments (
      id INTEGER PRIMARY KEY, public_id TEXT NOT NULL UNIQUE,
      user_id INTEGER NOT NULL REFERENCES users(id),
      purpose TEXT NOT NULL, ref_table TEXT NOT NULL, ref_id INTEGER NOT NULL,
      amount_paise INTEGER NOT NULL, currency TEXT NOT NULL,
      status TEXT NOT NULL, fulfillment TEXT NOT NULL,
      term_id INTEGER NOT NULL REFERENCES terms(id), created_at TEXT NOT NULL
    ) STRICT;
    """)
    # Apply 0005_store.sql
    sql = (MIGRATIONS_DIR / "0005_store.sql").read_text(encoding="utf-8")
    conn.executescript(sql)
    return conn


def test_store_variant_valid_stock():
    conn = get_db()
    conn.execute("INSERT INTO products VALUES (1, 'Club T-Shirt', 'Official merch', 500, 1, '2026-10-10T00:00:00Z')")
    
    # Positive: physical_qty >= reserved_qty
    conn.execute("INSERT INTO variants VALUES (1, 1, 'TSHIRT-BLK-M', 'M', 20, 5, '2026-10-10T00:00:00Z')")
    cur = conn.execute("SELECT physical_qty, reserved_qty FROM variants WHERE id = 1")
    assert cur.fetchone() == (20, 5)


def test_store_variant_invalid_stock_rejected():
    conn = get_db()
    conn.execute("INSERT INTO products VALUES (1, 'Club T-Shirt', 'Official merch', 500, 1, '2026-10-10T00:00:00Z')")
    
    # Negative: reserved_qty > physical_qty must fail CHECK (reserved_qty <= physical_qty)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO variants VALUES (1, 1, 'TSHIRT-BLK-L', 'L', 10, 11, '2026-10-10T00:00:00Z')")


def test_store_variant_unique_size_per_product():
    conn = get_db()
    conn.execute("INSERT INTO products VALUES (1, 'Club T-Shirt', 'Official merch', 500, 1, '2026-10-10T00:00:00Z')")
    conn.execute("INSERT INTO variants VALUES (1, 1, 'TSHIRT-BLK-M', 'M', 20, 0, '2026-10-10T00:00:00Z')")
    
    # Negative: duplicate (product_id, size) must fail UNIQUE
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO variants VALUES (2, 1, 'TSHIRT-RED-M', 'M', 15, 0, '2026-10-10T00:00:00Z')")


def test_store_order_item_unique_and_qty():
    conn = get_db()
    conn.execute("INSERT INTO users VALUES (1, 'carol@test.com', 'Carol', 'hash', 1, '2026-10-10T00:00:00Z')")
    conn.execute("INSERT INTO products VALUES (1, 'Club Hoodie', 'Hoodie', 1500, 1, '2026-10-10T00:00:00Z')")
    conn.execute("INSERT INTO variants VALUES (1, 1, 'HOODIE-M', 'M', 10, 2, '2026-10-10T00:00:00Z')")
    
    conn.execute("INSERT INTO merch_orders VALUES (1, 1, 'RESERVED', '2026-10-10T02:00:00Z', 3000, 'PUBLIC', NULL, NULL, NULL, '2026-10-10T00:00:00Z')")
    
    # Positive item insertion
    conn.execute("INSERT INTO merch_order_items VALUES (1, 1, 1, 2, 1500, '2026-10-10T00:00:00Z')")
    
    # Negative: duplicate (order_id, variant_id) must fail UNIQUE
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO merch_order_items VALUES (2, 1, 1, 1, 1500, '2026-10-10T00:00:00Z')")
    
    # Negative: qty > 10 must fail CHECK (qty BETWEEN 1 AND 10)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO merch_order_items VALUES (3, 1, 1, 11, 1500, '2026-10-10T00:00:00Z')")
