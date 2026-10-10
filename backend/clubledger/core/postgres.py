"""Supabase PostgreSQL adapter for the existing parameterized domain services.

The SQLite local workflow stays available. PostgreSQL transactions use a shared
advisory lock to preserve the original single-writer booking/ledger guarantees.
No credentials are embedded in this module.
"""

from decimal import Decimal
from pathlib import Path
import re
import sqlite3
import psycopg
from psycopg.pq import TransactionStatus
from clubledger.core.errors import MigrationChecksumError, MigrationGapError

import os
from psycopg import sql as pg_sql

SCHEMA = "clubledger"
WRITE_LOCK = 731940126


class Row:
    """Match SQLite rows: name/index lookup, value iteration, and dict(row)."""

    def __init__(self, columns, values):
        self.columns = columns
        self.values = tuple(
            int(v) if isinstance(v, Decimal) and v == int(v) else v for v in values
        )

    def keys(self):
        return self.columns

    def __getitem__(self, key):
        return (
            self.values[self.columns.index(key)]
            if isinstance(key, str)
            else self.values[key]
        )

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)


class Cursor:
    """Materialized result survives an autocommit transaction's completion."""

    def __init__(self, cursor, inserted=False):
        self.rowcount = cursor.rowcount
        self.description = cursor.description
        columns = [col.name for col in cursor.description] if cursor.description else []
        self.rows = (
            [Row(columns, r) for r in cursor.fetchall()] if cursor.description else []
        )
        self.lastrowid = self.rows[0][0] if inserted and self.rows else None
        self.index = 0

    def fetchone(self):
        if self.index == len(self.rows):
            return None
        row = self.rows[self.index]
        self.index += 1
        return row

    def fetchall(self):
        rows = self.rows[self.index :]
        self.index = len(self.rows)
        return rows

    def __iter__(self):
        return iter(self.fetchall())


def translate_sql(query):
    """Convert placeholders outside quoted strings and the few SQLite SQL forms."""
    query = re.sub(
        r"(\b(?:\w+\.)?email)\s*=\s*\?\s+COLLATE NOCASE",
        r"lower(\1) = lower(?)",
        query,
        flags=re.I,
    )
    query = query.replace(
        "sqlite_master",
        "(SELECT table_name AS name, 'table' AS type FROM information_schema.tables WHERE table_schema = current_schema()) AS sqlite_master",
    )
    result = []
    quote = None
    i = 0
    while i < len(query):
        char = query[i]
        if char in ("'", '"'):
            if quote == char and i + 1 < len(query) and query[i + 1] == char:
                result.append(char + char)
                i += 2
                continue
            quote = None if quote == char else char if quote is None else quote
        result.append(
            "%s" if char == "?" and quote is None else "%%" if char == "%" else char
        )
        i += 1
    return "".join(result)


class Connection:
    dialect = "postgres"

    def __init__(self, url):
        self.schema = os.environ.get("CLUBLEDGER_PG_SCHEMA", SCHEMA)
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", self.schema):
            raise ValueError("Invalid PostgreSQL schema name")
        self.raw = psycopg.connect(
            url, autocommit=True, prepare_threshold=None, connect_timeout=10
        )

    @property
    def in_transaction(self):
        return self.raw.info.transaction_status != TransactionStatus.IDLE

    def _setup(self, write=False):
        # Batch transaction settings to avoid three network round trips per query.
        settings = pg_sql.SQL(
            "SET LOCAL search_path TO {}, public; SET LOCAL statement_timeout = '25s'; SET LOCAL lock_timeout = '10s'"
        ).format(pg_sql.Identifier(self.schema))
        if write:
            settings += pg_sql.SQL("; SELECT pg_advisory_xact_lock({})").format(
                pg_sql.Literal(WRITE_LOCK)
            )
        self.raw.execute(settings, prepare=False)

    def execute(self, query, parameters=()):
        command = query.strip().rstrip(";").upper()
        if command in {"BEGIN", "BEGIN IMMEDIATE"}:
            self.raw.execute("BEGIN")
            self._setup(write=True)
            return Cursor(self.raw.cursor())
        if command in {"COMMIT", "ROLLBACK"}:
            cursor = self.raw.execute(command)
            return Cursor(cursor)
        sql = translate_sql(query)
        # Domain services expect lastrowid; PostgreSQL provides it with RETURNING.
        inserted = False
        match = re.match(r"\s*INSERT INTO (\w+)", query, re.I)
        if (
            match
            and match.group(1)
            not in {
                "schema_migrations",
                "role_permissions",
                "idempotency_keys",
                "receipt_content",
            }
            and "RETURNING" not in sql.upper()
        ):
            sql = sql.rstrip().rstrip(";") + " RETURNING id"
            inserted = True
        try:
            if self.in_transaction:
                return Cursor(self.raw.execute(sql, parameters), inserted)
            # Each standalone read/write gets its own transaction-local search path,
            # compatible with Supabase's transaction pooler and cold starts.
            with self.raw.transaction():
                self._setup(
                    write=bool(re.match(r"\s*(INSERT|UPDATE|DELETE)", query, re.I))
                )
                return Cursor(self.raw.execute(sql, parameters), inserted)
        except psycopg.IntegrityError as error:
            raise sqlite3.IntegrityError(error.diag.message_primary) from error

    def executemany(self, query, rows):
        for row in rows:
            self.execute(query, row)

    def commit(self):
        if self.in_transaction:
            self.raw.execute("COMMIT")

    def rollback(self):
        if self.in_transaction:
            self.raw.execute("ROLLBACK")

    def close(self):
        self.raw.close()


def apply_postgres_migrations(conn):
    """Apply checked-in PostgreSQL migrations, with checksum and gap checks."""
    from clubledger.paths import MIGRATIONS_DIR

    directory = MIGRATIONS_DIR.parent / "postgres"
    files = sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    import hashlib
    from clubledger.core import clock

    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    applied = (
        {
            r["number"]: r
            for r in conn.execute("SELECT * FROM schema_migrations").fetchall()
        }
        if exists
        else {}
    )
    if list(range(1, len(files) + 1)) != [int(p.name[:4]) for p in files]:
        raise MigrationGapError("PostgreSQL migration gap")
    results = []
    for p in files:
        content = p.read_text(encoding="utf-8")
        digest = hashlib.sha256(content.encode()).hexdigest()
        number = int(p.name[:4])
        if number in applied:
            if (
                applied[number]["checksum"] != digest
                or applied[number]["filename"] != p.name
            ):
                raise MigrationChecksumError("PostgreSQL migration changed: " + p.name)
            continue
        # Raw execution retains dollar-quoted PL/pgSQL functions as complete units.
        conn.raw.execute(content, prepare=False)
        conn.execute(
            "INSERT INTO schema_migrations(number,filename,checksum,applied_at) VALUES(?,?,?,?)",
            (number, p.name, digest, clock.now()),
        )
        results.append(number)
    return results
