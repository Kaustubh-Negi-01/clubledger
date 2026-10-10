"""Cloud tests use throwaway schemas in the dedicated Supabase project."""

import os
import uuid
import pytest
import psycopg
from psycopg import sql


@pytest.fixture
def temp_db_path(monkeypatch):
    url = os.environ.get("CLUBLEDGER_CLOUD_TEST_URL")
    if not url:
        pytest.skip("Set CLUBLEDGER_CLOUD_TEST_URL to test real PostgreSQL")
    schema = "clubledger_test_" + uuid.uuid4().hex[:16]
    monkeypatch.setenv("CLUBLEDGER_ENV", "test")
    monkeypatch.setenv("CLUBLEDGER_DATABASE_URL", url)
    monkeypatch.setenv("CLUBLEDGER_PG_SCHEMA", schema)
    monkeypatch.setenv("CLUBLEDGER_SIM_SECRET", "cloud-tests-only")
    with psycopg.connect(url, autocommit=True, prepare_threshold=None) as raw:
        raw.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        yield url
    finally:
        # Only the random schema created by this test is disposable.
        with psycopg.connect(url, autocommit=True, prepare_threshold=None) as raw:
            raw.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


@pytest.fixture
def db(temp_db_path):
    from clubledger.core.db import unit_of_work, connect, apply_migrations
    from clubledger.seed import seed_roles_and_permissions, seed_open_term
    from clubledger.membership.service import seed_plans

    with unit_of_work(temp_db_path) as conn:
        apply_migrations(conn)
        seed_roles_and_permissions(conn)
        seed_open_term(conn)
        seed_plans(conn)
    conn = connect(temp_db_path)
    try:
        yield conn
    finally:
        conn.close()
