"""Membership identifiers must resolve on PostgreSQL as well as SQLite."""

from clubledger.core import clock
from clubledger.membership.service import lookup_member


def test_postgres_member_lookup_by_code_and_qr_token(db, make_user):
    user = make_user(email="cloud-verification@college.edu")
    db.execute(
        "INSERT INTO memberships(user_id,plan_id,membership_year,status,starts_at,expires_at,member_code,qr_token,created_at) "
        "VALUES(?,1,'2026-27','ACTIVE','2026-08-01T00:00:00Z','2027-08-01T00:00:00Z','M-CLOUD-VERIFY','QR-CLOUD-VERIFY',?)",
        (user["id"], clock.now()),
    )

    by_code = lookup_member(db, code="M-CLOUD-VERIFY", at=clock.now())
    by_token = lookup_member(db, code="QR-CLOUD-VERIFY", at=clock.now())
    assert by_code.active and by_code.name == user["name"]
    assert by_token.active and by_token.name == user["name"]
