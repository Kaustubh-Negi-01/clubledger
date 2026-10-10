import sqlite3
import pytest

from clubledger.core.db import apply_migrations, connect


def get_migrated_db() -> sqlite3.Connection:
    conn = connect(":memory:")
    # Controlled-prefix genuine-file subset 0001..0005 per TURBO_B.txt
    applied = apply_migrations(
        conn,
        files=[
            "0001_core.sql",
            "0002_payments.sql",
            "0003_membership.sql",
            "0004_events.sql",
            "0005_store.sql",
        ],
    )
    assert applied == [1, 2, 3, 4, 5], f"Expected migrations 1..5, got {applied}"
    rerun = apply_migrations(
        conn,
        files=[
            "0001_core.sql",
            "0002_payments.sql",
            "0003_membership.sql",
            "0004_events.sql",
            "0005_store.sql",
        ],
    )
    assert rerun == [], f"Expected empty rerun, got {rerun}"
    return conn


def test_store_clean_migration_and_idempotent_rerun():
    conn = connect(":memory:")
    # Integration test validates the actual contiguous discovered migration sequence including 0006+
    applied = apply_migrations(conn)
    assert len(applied) >= 5
    assert applied[:5] == [1, 2, 3, 4, 5]
    rerun = apply_migrations(conn)
    assert rerun == [], f"Expected empty rerun, got {rerun}"

    rows = conn.execute(
        "SELECT number, filename FROM schema_migrations ORDER BY number ASC;"
    ).fetchall()
    numbers = [r["number"] for r in rows]
    assert numbers[:5] == [1, 2, 3, 4, 5]
    row_store = [r for r in rows if r["number"] == 5][0]
    assert row_store["filename"] == "0005_store.sql"
    conn.close()


def test_store_variant_valid_stock():
    conn = get_migrated_db()
    try:
        conn.execute(
            "INSERT INTO products (id, name, description, base_price_paise, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (1, "Club T-Shirt", "Official merch", 500, 1, "2026-10-10T00:00:00Z"),
        )
        # Positive: physical_qty >= reserved_qty
        conn.execute(
            "INSERT INTO variants (id, product_id, sku, size, physical_qty, reserved_qty, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?);",
            (1, 1, "TSHIRT-BLK-M", "M", 20, 5, "2026-10-10T00:00:00Z"),
        )
        row = conn.execute(
            "SELECT physical_qty, reserved_qty FROM variants WHERE id = 1;"
        ).fetchone()
        assert row["physical_qty"] == 20
        assert row["reserved_qty"] == 5
    finally:
        conn.close()


def test_store_variant_invalid_stock_rejected():
    conn = get_migrated_db()
    try:
        conn.execute(
            "INSERT INTO products (id, name, description, base_price_paise, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (1, "Club T-Shirt", "Official merch", 500, 1, "2026-10-10T00:00:00Z"),
        )
        # Negative: reserved_qty > physical_qty must fail CHECK (reserved_qty <= physical_qty)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO variants (id, product_id, sku, size, physical_qty, reserved_qty, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?);",
                (1, 1, "TSHIRT-BLK-L", "L", 10, 11, "2026-10-10T00:00:00Z"),
            )
    finally:
        conn.close()


def test_store_variant_unique_size_per_product():
    conn = get_migrated_db()
    try:
        conn.execute(
            "INSERT INTO products (id, name, description, base_price_paise, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (1, "Club T-Shirt", "Official merch", 500, 1, "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO variants (id, product_id, sku, size, physical_qty, reserved_qty, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?);",
            (1, 1, "TSHIRT-BLK-M", "M", 20, 0, "2026-10-10T00:00:00Z"),
        )
        # Negative: duplicate (product_id, size) must fail UNIQUE
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO variants (id, product_id, sku, size, physical_qty, reserved_qty, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?);",
                (2, 1, "TSHIRT-RED-M", "M", 15, 0, "2026-10-10T00:00:00Z"),
            )
    finally:
        conn.close()


def test_store_order_item_unique_and_qty():
    conn = get_migrated_db()
    try:
        conn.execute(
            "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (1, "carol@test.com", "Carol", "scrypt_hash", 1, "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO products (id, name, description, base_price_paise, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (1, "Club Hoodie", "Hoodie", 1500, 1, "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO variants (id, product_id, sku, size, physical_qty, reserved_qty, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?);",
            (1, 1, "HOODIE-M", "M", 10, 2, "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO merch_orders (id, user_id, status, expires_at, total_paise, price_tier, payment_id, picked_up_at, picked_up_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (
                1,
                1,
                "RESERVED",
                "2026-10-10T02:00:00Z",
                3000,
                "PUBLIC",
                None,
                None,
                None,
                "2026-10-10T00:00:00Z",
            ),
        )

        # Positive item insertion
        conn.execute(
            "INSERT INTO merch_order_items (id, order_id, variant_id, qty, unit_price_paise, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (1, 1, 1, 2, 1500, "2026-10-10T00:00:00Z"),
        )

        # Negative: duplicate (order_id, variant_id) must fail UNIQUE
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO merch_order_items (id, order_id, variant_id, qty, unit_price_paise, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?);",
                (2, 1, 1, 1, 1500, "2026-10-10T00:00:00Z"),
            )

        # Negative: qty > 10 must fail CHECK (qty BETWEEN 1 AND 10)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO merch_order_items (id, order_id, variant_id, qty, unit_price_paise, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?);",
                (3, 1, 1, 11, 1500, "2026-10-10T00:00:00Z"),
            )
    finally:
        conn.close()
