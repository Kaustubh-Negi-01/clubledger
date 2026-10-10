"""Explicit, transactional append of synthetic data to an initialized database.

No resets, migrations, deletes, global settlement or existing-account purchases.
The caller provides the configured database connection; no credentials live here.
"""

import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from database.scripts.create_large_demo import BUSINESS_TABLES, populate
from clubledger.core import clock
from clubledger.reports.service import check_integrity

VERSION = "large-demo-v1"


def snapshots(conn):
    """Fingerprints of records, including opaque receipt bytes; never log values."""
    result = {}
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    for row in tables:
        table = row[0]
        if table.startswith("sqlite_") or table in {"sessions", "rate_limit_attempts"}:
            continue
        result[table] = {
            hashlib.sha256(
                json.dumps(dict(record), sort_keys=True, default=str).encode()
            ).hexdigest()
            for record in conn.execute(f'SELECT * FROM "{table}"')
        }
    return result


def append_dataset(conn):
    """Caller must wrap this in unit_of_work so failures roll back atomically."""
    admin = conn.execute(
        "SELECT id FROM users WHERE email='admin@skyline.edu'"
    ).fetchone()[0]
    marker = conn.execute(
        "SELECT 1 FROM idempotency_keys WHERE actor_user_id=? AND action='demo.seed' AND key=?",
        (admin, VERSION),
    ).fetchone()
    if marker:
        return {"added": False, "reason": "Dataset already added; no changes made."}
    if conn.execute(
        "SELECT 1 FROM users WHERE email LIKE 'dataset%@demo.example'"
    ).fetchone():
        raise RuntimeError(
            "Dataset namespace already exists without completion marker; stopped without overwriting."
        )
    checks = check_integrity(conn)
    if not checks["passed"]:
        raise RuntimeError("Existing database integrity failed; no data appended.")
    if getattr(conn, "dialect", None) == "postgres":
        # The legacy gala seed inserted ID 1 explicitly. Advance only its identity
        # counter with ordinary sequence USAGE so new events cannot collide.
        # Gaps in IDs are harmless; no old event is rewritten and no DDL is used.
        highest = conn.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]
        while (
            conn.execute(
                "SELECT nextval(pg_get_serial_sequence('events','id'))"
            ).fetchone()[0]
            <= highest
        ):
            pass
    before = snapshots(conn)
    counts_before = {
        t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        for t in BUSINESS_TABLES
    }
    populate(conn, additive=True)
    after = snapshots(conn)
    for table, fingerprints in before.items():
        if not fingerprints.issubset(after.get(table, set())):
            raise RuntimeError(
                f"An existing {table} record changed; entire append rolled back."
            )
    checks = check_integrity(conn)
    if not checks["passed"]:
        raise RuntimeError(f"New dataset integrity failed: {checks['failures']}")
    counts_after = {
        t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        for t in BUSINESS_TABLES
    }
    added = {t: counts_after[t] - counts_before[t] for t in BUSINESS_TABLES}
    if sum(added.values()) < 250:
        raise RuntimeError(
            "Fewer than 250 meaningful records were added; rollback required."
        )
    conn.execute(
        "INSERT INTO idempotency_keys(actor_user_id,action,key,request_hash,result_ref,created_at) VALUES(?,'demo.seed',?,?,?,?)",
        (
            admin,
            VERSION,
            hashlib.sha256(VERSION.encode()).hexdigest(),
            "seed:" + VERSION,
            clock.now(),
        ),
    )
    return {
        "added": True,
        "added_counts": added,
        "added_business_records": sum(added.values()),
        "business_counts": counts_after,
        "existing_records_preserved": True,
        "integrity": checks,
    }
