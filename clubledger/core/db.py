"""Database connection, transactions (unit of work), and migrations per CONTRACT.md G5, G6, §1, §13.3."""

from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import sqlite3
from typing import Iterator

from clubledger.config import get_db_path
from clubledger.core import clock
from clubledger.core.errors import (
    MigrationChecksumError,
    MigrationDuplicateError,
    MigrationError,
    MigrationGapError,
)


MIGRATION_PATTERN = re.compile(r"^(\d{4})_.*\.sql$")


def connect(path: str) -> sqlite3.Connection:
    """Connect to SQLite with pragmas per CONTRACT G6.

    Pragmas: foreign_keys=ON, journal_mode=WAL, busy_timeout=5000, synchronous=NORMAL.
    Uses autocommit=True so outer transactions can be explicitly controlled via
    BEGIN IMMEDIATE / COMMIT / ROLLBACK.
    """
    if path != ":memory:":
        db_file = Path(path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path, autocommit=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    # WAL is supported on file-backed databases; on :memory: it evaluates to 'memory'
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


@contextmanager
def unit_of_work(path: str | None = None) -> Iterator[sqlite3.Connection]:
    """Single outer transaction context manager per CONTRACT G5 and §13.

    Issues BEGIN IMMEDIATE, commits on clean exit, rolls back on exception.
    """
    db_path = path if path is not None else get_db_path()
    conn = connect(db_path)
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def split_sql_statements(sql: str) -> list[str]:
    """Split SQL script into executable statements without using sqlite3.executescript.

    Uses sqlite3.complete_statement to preserve trigger definitions and string literals.
    """
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        stripped = buffer.strip()
        if stripped and sqlite3.complete_statement(buffer):
            # Check if there is executable SQL (not purely comments)
            has_sql = any(
                sub.strip() and not sub.strip().startswith("--")
                for sub in stripped.splitlines()
            )
            if has_sql:
                statements.append(stripped)
            buffer = ""

    leftover = buffer.strip()
    if leftover:
        has_sql = any(
            sub.strip() and not sub.strip().startswith("--")
            for sub in leftover.splitlines()
        )
        if has_sql:
            statements.append(leftover)

    return statements


def calculate_checksum(content: str) -> str:
    """Calculate SHA-256 checksum of SQL content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _get_default_migrations_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "migrations"


def get_available_migrations(migrations_dir: Path | None = None) -> list[tuple[int, str, Path]]:
    """Return sorted list of (number, filename, path) for valid migrations.

    Raises MigrationDuplicateError if duplicate migration numbers are found.
    """
    dir_path = migrations_dir or _get_default_migrations_dir()
    if not dir_path.exists():
        return []

    seen_numbers: dict[int, str] = {}
    migrations: list[tuple[int, str, Path]] = []
    for file in dir_path.iterdir():
        if not file.is_file():
            continue
        match = MIGRATION_PATTERN.match(file.name)
        if match:
            num = int(match.group(1))
            if num in seen_numbers:
                raise MigrationDuplicateError(
                    f"Duplicate migration number {num:04d}: found in '{seen_numbers[num]}' and '{file.name}'"
                )
            seen_numbers[num] = file.name
            migrations.append((num, file.name, file))

    migrations.sort(key=lambda m: m[0])
    return migrations


def apply_migrations(
    conn: sqlite3.Connection,
    migrations_dir: Path | None = None,
    *,
    files: list[str | Path] | None = None,
) -> list[int]:
    """Apply migrations to database.

    - If files is None: applies the contiguous available prefix strictly by number,
      rejecting internal gaps, duplicate numbers, and missing/renamed/changed applied files
      BEFORE applying anything.
    - If files is specified: test-only subset fixture mode applying exactly the named files.
    """
    # 1. Determine migration files to consider
    dir_path = migrations_dir or _get_default_migrations_dir()
    migration_items: list[tuple[int, str, Path]] = []

    if files is not None:
        # Test-only subset mode
        for f in files:
            path = Path(f) if Path(f).is_absolute() else dir_path / f
            if not path.exists():
                raise FileNotFoundError(f"Migration file not found: {path}")
            match = MIGRATION_PATTERN.match(path.name)
            if not match:
                raise ValueError(f"Invalid migration filename format: {path.name}")
            num = int(match.group(1))
            migration_items.append((num, path.name, path))
        migration_items.sort(key=lambda m: m[0])
    else:
        # Standard contiguous prefix mode (rejects duplicate numbers via get_available_migrations)
        migration_items = get_available_migrations(dir_path)

    # 2. Check schema_migrations table and validate applied migrations
    applied_table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations';"
    ).fetchone() is not None

    applied_map: dict[int, tuple[str, str]] = {}
    if applied_table_exists:
        rows = conn.execute(
            "SELECT number, filename, checksum FROM schema_migrations ORDER BY number ASC;"
        ).fetchall()
        for r in rows:
            applied_map[r["number"]] = (r["filename"], r["checksum"])

    # 3. Check for missing, renamed, or modified applied migrations BEFORE applying anything
    item_map = {num: (name, path) for num, name, path in migration_items}
    for applied_num, (applied_name, stored_checksum) in applied_map.items():
        if files is None:
            # In standard CLI mode, previously applied files must exist and keep their filename
            if applied_num not in item_map:
                raise MigrationError(
                    f"Previously applied migration file missing: {applied_name} (number {applied_num:04d})"
                )
            current_name, file_path = item_map[applied_num]
            if current_name != applied_name:
                raise MigrationError(
                    f"Previously applied migration file renamed: expected {applied_name}, found {current_name} (number {applied_num:04d})"
                )
            current_checksum = calculate_checksum(file_path.read_text(encoding="utf-8"))
            if current_checksum != stored_checksum:
                raise MigrationChecksumError(
                    f"Checksum mismatch for migration {applied_name}: "
                    f"stored {stored_checksum}, current {current_checksum}"
                )
        else:
            # In test-only subset mode, validate checksum only if the file is in the explicit subset
            if applied_num in item_map:
                _, file_path = item_map[applied_num]
                current_checksum = calculate_checksum(file_path.read_text(encoding="utf-8"))
                if current_checksum != stored_checksum:
                    raise MigrationChecksumError(
                        f"Checksum mismatch for migration {applied_name}: "
                        f"stored {stored_checksum}, current {current_checksum}"
                    )

    # 4. In standard CLI mode, validate contiguous prefix / internal gaps across available files
    if files is None:
        if not migration_items:
            return []
        max_num = max(num for num, _, _ in migration_items)
        present_nums = {num for num, _, _ in migration_items}
        for expected in range(1, max_num + 1):
            if expected not in present_nums:
                raise MigrationGapError(
                    f"Internal migration gap detected: missing {expected:04d}"
                )

    # 4. Filter migrations that need to be applied
    to_apply = [item for item in migration_items if item[0] not in applied_map]
    if not to_apply:
        return []

    # 5. Apply each migration transactionally
    applied_now: list[int] = []
    own_transaction = not conn.in_transaction

    for num, filename, file_path in to_apply:
        content = file_path.read_text(encoding="utf-8")
        checksum = calculate_checksum(content)
        statements = split_sql_statements(content)

        if own_transaction:
            conn.execute("BEGIN IMMEDIATE")
        try:
            for stmt in statements:
                conn.execute(stmt)

            # Record in schema_migrations
            conn.execute(
                "INSERT INTO schema_migrations (number, filename, checksum, applied_at) "
                "VALUES (?, ?, ?, ?);",
                (num, filename, checksum, clock.now()),
            )
            if own_transaction:
                conn.execute("COMMIT")
            applied_now.append(num)
        except Exception:
            if own_transaction and conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    return applied_now
