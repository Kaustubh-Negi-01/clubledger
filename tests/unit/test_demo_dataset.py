"""The reviewer dataset must preserve old purchases and never duplicate on retry."""

from database.scripts.append_large_demo import append_dataset, snapshots
from clubledger.seed import seed_all
from clubledger.membership.service import start_join
from clubledger.events.service import create_hold


def test_large_demo_append_preserves_existing_data_and_is_repeat_safe(db):
    from clubledger.core import clock

    # Match the real operator's all-or-nothing transaction boundary.
    db.execute("BEGIN IMMEDIATE")
    try:
        _verify_append(db)
    finally:
        db.execute("ROLLBACK")
        clock.reset()


def _verify_append(db):
    seed_all(db, demo=True)
    student = db.execute(
        "SELECT id FROM users WHERE email='student@skyline.edu'"
    ).fetchone()[0]
    # Existing pending purchases must survive the seed's expiry/settlement steps.
    dues = start_join(db, student, 1, "old-student-dues")
    hold, ticket_payment = create_hold(db, student, 1, 2, "old-student-hold")
    before = snapshots(db)
    result = append_dataset(db)
    assert result["added_business_records"] == 254
    assert result["integrity"]["passed"]
    assert (
        db.execute(
            "SELECT COUNT(*) FROM payments WHERE settled_at IS NOT NULL"
        ).fetchone()[0]
        >= 80
    )
    assert (
        db.execute(
            "SELECT COUNT(*) FROM merch_orders WHERE status='EXPIRED'"
        ).fetchone()[0]
        == 5
    )
    after = snapshots(db)
    for table, records in before.items():
        assert records.issubset(after[table])
    assert (
        db.execute("SELECT status FROM payments WHERE id=?", (dues.id,)).fetchone()[0]
        == "CREATED"
    )
    assert (
        db.execute(
            "SELECT status FROM payments WHERE id=?", (ticket_payment.id,)
        ).fetchone()[0]
        == "CREATED"
    )
    assert (
        db.execute("SELECT status FROM ticket_holds WHERE id=?", (hold.id,)).fetchone()[
            0
        ]
        == "HELD"
    )
    assert append_dataset(db)["added"] is False
    assert snapshots(db) == after
