"""CLI command dispatcher for ClubLedger per CONTRACT.md §14."""

import argparse
import os
import sys
from typing import Sequence

from clubledger.config import get_config
from clubledger.core import clock
from clubledger.core.db import apply_migrations, unit_of_work


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="clubledger", description="ClubLedger CLI")
    parser.add_argument("--db", type=str, default=None, help="Path to SQLite database file")
    parser.add_argument("--as-of", type=str, default=None, help="Simulate execution as of ISO timestamp")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Apply pending database migrations strictly by number")
    migrate_parser.add_argument("--db", type=str, default=None, help="Path to SQLite database file")
    migrate_parser.add_argument("--as-of", type=str, default=None, help="Simulate execution as of ISO timestamp")

    # seed command
    seed_parser = subparsers.add_parser("seed", help="Seed roles and permissions")
    seed_parser.add_argument("--db", type=str, default=None, help="Path to SQLite database file")
    seed_parser.add_argument("--as-of", type=str, default=None, help="Simulate execution as of ISO timestamp")
    seed_parser.add_argument("--demo", action="store_true", help="Seed demo data")

    # start command
    start_parser = subparsers.add_parser("start", help="Start the ClubLedger web application server")
    start_parser.add_argument("--host", type=str, default=None, help="Bind host")
    start_parser.add_argument("--port", type=int, default=None, help="Bind port")

    # settle command
    settle_parser = subparsers.add_parser("settle", help="Settle eligible payments and unapplied receipts")
    settle_parser.add_argument("--db", type=str, default=None, help="Path to SQLite database file")
    settle_parser.add_argument("--as-of", type=str, default=None, help="Simulate execution as of ISO timestamp")

    # expire-holds command
    expire_parser = subparsers.add_parser("expire-holds", help="Expire stale holds, orders, and payments")
    expire_parser.add_argument("--db", type=str, default=None, help="Path to SQLite database file")
    expire_parser.add_argument("--as-of", type=str, default=None, help="Simulate execution as of ISO timestamp")

    # check-integrity command
    integrity_parser = subparsers.add_parser("check-integrity", help="Run accounting and system integrity checks")
    integrity_parser.add_argument("--db", type=str, default=None, help="Path to SQLite database file")

    return parser.parse_args(argv)


def handle_migrate(db_path: str | None = None) -> int:
    config = get_config()
    target_db = db_path or config.db_path

    with unit_of_work(target_db) as conn:
        applied = apply_migrations(conn)

    if applied:
        print(f"Applied migrations: {applied}")
    else:
        print("Database is up to date. No pending migrations.")
    return 0


def handle_seed(db_path: str | None = None, demo: bool = False) -> int:
    from clubledger.seed import seed_all

    config = get_config()
    target_db = db_path or config.db_path

    with unit_of_work(target_db) as conn:
        seed_all(conn, demo=demo)

    print("Seeded roles and permissions successfully.")
    return 0


def handle_start(host: str | None = None, port: int | None = None) -> int:
    import uvicorn
    from clubledger.config import get_config, validate_server_binding

    config = get_config()
    target_host = host or config.host
    target_port = port or config.port

    try:
        validate_server_binding(target_host, config.env)
    except ValueError as e:
        print(f"Server startup error: {e}", file=sys.stderr)
        return 1

    print(f"Starting ClubLedger server on {target_host}:{target_port} ({config.env})...")
    uvicorn.run("clubledger.main:app", host=target_host, port=target_port)
    return 0


def handle_settle(db_path: str | None = None, as_of: str | None = None) -> int:
    from clubledger.payments.service import settle_payments

    config = get_config()
    target_db = db_path or config.db_path
    as_of_ts = as_of or clock.now()

    with unit_of_work(target_db) as conn:
        count = settle_payments(conn, as_of=as_of_ts)

    print(f"Settled {count} items as of {as_of_ts}.")
    return 0


def handle_expire_holds(db_path: str | None = None, as_of: str | None = None) -> int:
    from clubledger.payments.service import expire_payments

    config = get_config()
    target_db = db_path or config.db_path
    as_of_ts = as_of or clock.now()

    with unit_of_work(target_db) as conn:
        p_count = expire_payments(conn, as_of=as_of_ts)
        # Call events and store expire hooks if available
        try:
            from clubledger.events.service import expire_holds
            expire_holds(conn, as_of=as_of_ts)
        except (ImportError, AttributeError):
            pass
        try:
            from clubledger.store.service import expire_orders
            expire_orders(conn, as_of=as_of_ts)
        except (ImportError, AttributeError):
            pass

    print(f"Expired {p_count} payments as of {as_of_ts}.")
    return 0


def handle_check_integrity(db_path: str | None = None) -> int:
    from clubledger.reports.service import check_integrity

    config = get_config()
    target_db = db_path or config.db_path

    with unit_of_work(target_db) as conn:
        # Require schema tables to exist; an empty database is not valid
        required_tables = {"terms", "accounts", "journal_entries", "journal_lines", "payments"}
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = {row[0] for row in cur.fetchall()}
        missing_tables = required_tables - existing_tables
        if missing_tables:
            print(f"Integrity check failed: Missing required schema tables: {sorted(missing_tables)}", file=sys.stderr)
            return 1

        res = check_integrity(conn)
        if not res.get("passed") or res.get("failures"):
            print(f"Integrity check failed: {res.get('failures')}", file=sys.stderr)
            for name, details in res.get("checks", {}).items():
                if details.get("status") == "FAIL":
                    print(f"  {name}: {details.get('detail')}", file=sys.stderr)
            return 1

        # Required checks must not be UNIMPLEMENTED
        required_checks = ["debits_equal_credits", "succeeded_payments_received_entry", "source_links_integrity"]
        for chk in required_checks:
            chk_status = res.get("checks", {}).get(chk, {}).get("status")
            if chk_status != "PASS":
                print(f"Integrity check failed: Required check '{chk}' did not pass (status: {chk_status})", file=sys.stderr)
                return 1

    print("Integrity checks passed.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    if args.as_of:
        env = os.environ.get("CLUBLEDGER_ENV", "dev").lower()
        if env not in {"dev", "test"}:
            print(f"Error: --as-of is permitted only in 'dev' or 'test' environments, not '{env}'.", file=sys.stderr)
            return 1
        if env == "test":
            clock.set_now(args.as_of)

    target_db = getattr(args, "db", None)

    if args.command == "migrate":
        return handle_migrate(target_db)
    if args.command == "seed":
        return handle_seed(target_db, demo=getattr(args, "demo", False))
    if args.command == "start":
        return handle_start(args.host, args.port)
    if args.command == "settle":
        return handle_settle(target_db, args.as_of)
    if args.command == "expire-holds":
        return handle_expire_holds(target_db, args.as_of)
    if args.command == "check-integrity":
        return handle_check_integrity(target_db)

    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
