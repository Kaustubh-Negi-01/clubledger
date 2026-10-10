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

    return parser.parse_args(argv)


def handle_migrate(db_path: str | None = None) -> int:
    config = get_config()
    target_db = db_path or config.db_path

    # Apply migrations inside unit_of_work
    with unit_of_work(target_db) as conn:
        applied = apply_migrations(conn)

    if applied:
        print(f"Applied migrations: {applied}")
    else:
        print("Database is up to date. No pending migrations.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    # G9: CLI --as-of is honored only when CLUBLEDGER_ENV is dev or test
    if args.as_of:
        env = os.environ.get("CLUBLEDGER_ENV", "dev").lower()
        if env not in {"dev", "test"}:
            print(f"Error: --as-of is permitted only in 'dev' or 'test' environments, not '{env}'.", file=sys.stderr)
            return 1
        clock.set_now(args.as_of)

    if args.command == "migrate":
        return handle_migrate(args.db)

    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
