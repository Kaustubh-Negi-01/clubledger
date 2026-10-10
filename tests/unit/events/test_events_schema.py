import sqlite3
import pytest

from clubledger.core.db import apply_migrations, connect


def get_migrated_db() -> sqlite3.Connection:
    conn = connect(":memory:")
    applied = apply_migrations(conn)
    assert applied == [1, 2, 3, 4, 5], f"Expected migrations 1..5, got {applied}"
    rerun = apply_migrations(conn)
    assert rerun == [], f"Expected empty rerun, got {rerun}"
    return conn


def test_events_clean_migration_and_idempotent_rerun():
    conn = get_migrated_db()
    rows = conn.execute(
        "SELECT number, filename FROM schema_migrations ORDER BY number ASC;"
    ).fetchall()
    assert [r["number"] for r in rows] == [1, 2, 3, 4, 5]
    assert rows[3]["filename"] == "0004_events.sql"
    conn.close()


def test_multi_seat_hold_and_ticket_uniqueness():
    conn = get_migrated_db()
    try:
        conn.execute(
            "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (1, "bob@test.com", "Bob", "scrypt_hash", 1, "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO terms (id, label, starts_at, ends_at, status, closed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?);",
            (1, "Term 1", "2026-08-01T00:00:00Z", None, "OPEN", None, "2026-08-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO payments (id, public_id, user_id, purpose, ref_table, ref_id, amount_paise, currency, status, fulfillment, term_id, succeeded_at, settled_at, refunded_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (1, "pay_evt_1", 1, "TICKET", "ticket_holds", 1, 1000, "INR", "SUCCEEDED", "FULFILLED", 1, "2026-10-10T00:00:00Z", None, None, "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO events (id, term_id, title, venue, starts_at, ends_at, capacity, member_price_paise, public_price_paise, max_per_order, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (1, 1, "Annual Gala", "Main Hall", "2026-11-01T18:00:00Z", "2026-11-01T22:00:00Z", 100, 500, 800, 4, "ON_SALE", "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO ticket_holds (id, event_id, user_id, qty, unit_price_paise, price_tier, status, expires_at, released_at, consumed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (1, 1, 1, 2, 500, "MEMBER", "CONSUMED", "2026-10-10T01:00:00Z", None, "2026-10-10T00:10:00Z", "2026-10-10T00:00:00Z"),
        )

        # Positive: Two distinct seats in one hold (seat_index 1 and 2)
        conn.execute(
            "INSERT INTO tickets (id, event_id, hold_id, seat_index, user_id, payment_id, code, price_paise, price_tier, status, used_at, used_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (1, 1, 1, 1, 1, 1, "CODE_SEAT_1", 500, "MEMBER", "ISSUED", None, None, "2026-10-10T00:10:00Z"),
        )
        conn.execute(
            "INSERT INTO tickets (id, event_id, hold_id, seat_index, user_id, payment_id, code, price_paise, price_tier, status, used_at, used_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (2, 1, 1, 2, 1, 1, "CODE_SEAT_2", 500, "MEMBER", "ISSUED", None, None, "2026-10-10T00:10:00Z"),
        )

        count = conn.execute("SELECT count(*) FROM tickets WHERE hold_id = 1;").fetchone()[0]
        assert count == 2

        # Negative: Re-inserting duplicate seat_index 1 for the same hold_id must violate UNIQUE (hold_id, seat_index)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO tickets (id, event_id, hold_id, seat_index, user_id, payment_id, code, price_paise, price_tier, status, used_at, used_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                (3, 1, 1, 1, 1, 1, "CODE_SEAT_DUPE", 500, "MEMBER", "ISSUED", None, None, "2026-10-10T00:10:00Z"),
            )
    finally:
        conn.close()


def test_ticket_paid_requires_payment_id():
    conn = get_migrated_db()
    try:
        conn.execute(
            "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (1, "bob@test.com", "Bob", "scrypt_hash", 1, "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO terms (id, label, starts_at, ends_at, status, closed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?);",
            (1, "Term 1", "2026-08-01T00:00:00Z", None, "OPEN", None, "2026-08-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO events (id, term_id, title, venue, starts_at, ends_at, capacity, member_price_paise, public_price_paise, max_per_order, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (1, 1, "Gala", "Hall", "2026-11-01T18:00:00Z", "2026-11-01T22:00:00Z", 100, 500, 800, 4, "ON_SALE", "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO ticket_holds (id, event_id, user_id, qty, unit_price_paise, price_tier, status, expires_at, released_at, consumed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (1, 1, 1, 1, 500, "MEMBER", "CONSUMED", "2026-10-10T01:00:00Z", None, "2026-10-10T00:10:00Z", "2026-10-10T00:00:00Z"),
        )

        # Paid ticket (price_paise = 500) with payment_id = NULL must fail CHECK (price_paise = 0 OR payment_id IS NOT NULL)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO tickets (id, event_id, hold_id, seat_index, user_id, payment_id, code, price_paise, price_tier, status, used_at, used_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                (1, 1, 1, 1, 1, None, "CODE_NO_PAY", 500, "MEMBER", "ISSUED", None, None, "2026-10-10T00:10:00Z"),
            )
    finally:
        conn.close()


def test_free_ticket_allows_null_payment_id():
    conn = get_migrated_db()
    try:
        conn.execute(
            "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (1, "bob@test.com", "Bob", "scrypt_hash", 1, "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO terms (id, label, starts_at, ends_at, status, closed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?);",
            (1, "Term 1", "2026-08-01T00:00:00Z", None, "OPEN", None, "2026-08-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO events (id, term_id, title, venue, starts_at, ends_at, capacity, member_price_paise, public_price_paise, max_per_order, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (1, 1, "Free Seminar", "Hall", "2026-11-01T18:00:00Z", "2026-11-01T22:00:00Z", 100, 0, 0, 4, "ON_SALE", "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO ticket_holds (id, event_id, user_id, qty, unit_price_paise, price_tier, status, expires_at, released_at, consumed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (1, 1, 1, 1, 0, "PUBLIC", "CONSUMED", "2026-10-10T01:00:00Z", None, "2026-10-10T00:10:00Z", "2026-10-10T00:00:00Z"),
        )

        # Free ticket (price_paise = 0) with payment_id = NULL must succeed
        conn.execute(
            "INSERT INTO tickets (id, event_id, hold_id, seat_index, user_id, payment_id, code, price_paise, price_tier, status, used_at, used_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (1, 1, 1, 1, 1, None, "CODE_FREE", 0, "PUBLIC", "ISSUED", None, None, "2026-10-10T00:10:00Z"),
        )
        row = conn.execute(
            "SELECT price_paise, payment_id FROM tickets WHERE id = 1;"
        ).fetchone()
        assert row["price_paise"] == 0
        assert row["payment_id"] is None
    finally:
        conn.close()


def test_ticket_used_status_requires_used_at():
    conn = get_migrated_db()
    try:
        conn.execute(
            "INSERT INTO users (id, email, name, password_hash, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (1, "bob@test.com", "Bob", "scrypt_hash", 1, "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO terms (id, label, starts_at, ends_at, status, closed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?);",
            (1, "Term 1", "2026-08-01T00:00:00Z", None, "OPEN", None, "2026-08-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO events (id, term_id, title, venue, starts_at, ends_at, capacity, member_price_paise, public_price_paise, max_per_order, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (1, 1, "Free Seminar", "Hall", "2026-11-01T18:00:00Z", "2026-11-01T22:00:00Z", 100, 0, 0, 4, "ON_SALE", "2026-10-10T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO ticket_holds (id, event_id, user_id, qty, unit_price_paise, price_tier, status, expires_at, released_at, consumed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (1, 1, 1, 1, 0, "PUBLIC", "CONSUMED", "2026-10-10T01:00:00Z", None, "2026-10-10T00:10:00Z", "2026-10-10T00:00:00Z"),
        )

        # status = 'USED' but used_at IS NULL must fail CHECK ((status = 'USED') = (used_at IS NOT NULL))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO tickets (id, event_id, hold_id, seat_index, user_id, payment_id, code, price_paise, price_tier, status, used_at, used_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                (1, 1, 1, 1, 1, None, "CODE_USED_NO_DATE", 0, "PUBLIC", "USED", None, None, "2026-10-10T00:10:00Z"),
            )
    finally:
        conn.close()
