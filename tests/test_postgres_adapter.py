"""The adapter must preserve parameter and row semantics used by domain services."""

from clubledger.core.postgres import Row, translate_sql
from decimal import Decimal


def test_postgres_placeholders_preserve_literals():
    assert (
        translate_sql("SELECT '?' AS literal, ? AS value, '50%' AS label")
        == "SELECT '?' AS literal, %s AS value, '50%%' AS label"
    )


def test_postgres_rows_support_names_positions_and_unpacking():
    row = Row(["id", "total"], [3, Decimal(1200)])
    assert row[0] == row["id"] == 3
    assert tuple(row) == (3, 1200)
    assert dict(row) == {"id": 3, "total": 1200}
    assert isinstance(row["total"], int)


def test_postgres_case_insensitive_email_lookup():
    assert (
        translate_sql("SELECT id FROM users WHERE email = ? COLLATE NOCASE;")
        == "SELECT id FROM users WHERE lower(email) = lower(%s);"
    )
