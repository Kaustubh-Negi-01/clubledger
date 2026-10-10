"""Create an isolated SQLite reviewer demo, never modify an existing database.

Run from the repository root with the project's Python interpreter. Catalog
records are inserted directly; purchases and accounting use the real services.
All people, purchases and receipts are synthetic. No network calls are made.
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = ROOT / "database/runtime/large-demo"
DB = DEMO_DIR / "clubledger-large-demo.db"
BUSINESS_TABLES = (
    "users",
    "memberships",
    "events",
    "tickets",
    "products",
    "merch_orders",
    "expenses",
    "fundraisers",
    "tasks",
    "announcements",
)


def receipt_pdf(number, amount):
    """Generate a viewable one-page PDF, clearly marked as a fake receipt."""
    text = f"SYNTHETIC DEMO RECEIPT {number} - INR {amount / 100:.2f} - NOT A REAL PURCHASE"
    stream = f"BT /F1 12 Tf 40 740 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
    ]
    result = b"%PDF-1.4\n"
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(result))
        result += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    position = len(result)
    result += b"xref\n0 6\n0000000000 65535 f \n"
    result += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    result += (
        f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{position}\n%%EOF\n".encode()
    )
    return result


def configure_local():
    # Empty URL overrides any root .env cloud URL; the explicit SQLite path wins.
    os.environ.update(
        CLUBLEDGER_ENV="dev",
        CLUBLEDGER_DATABASE_URL="",
        CLUBLEDGER_DB_PATH=str(DB),
        CLUBLEDGER_RECEIPTS_DIR=str(DEMO_DIR / "receipts"),
        CLUBLEDGER_SIM_SECRET="isolated-local-synthetic-demo-only",
    )
    sys.path.insert(0, str(ROOT / "backend"))


def report(conn):
    from clubledger.reports.service import check_integrity

    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    counts = {
        table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        for table in tables
    }
    checks = check_integrity(conn)
    foreign_keys = [tuple(row) for row in conn.execute("PRAGMA foreign_key_check")]
    assert checks["passed"] and not checks["failures"], checks
    assert not foreign_keys, foreign_keys
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    meaningful = sum(counts[table] for table in BUSINESS_TABLES)
    assert meaningful >= 250, meaningful
    return {
        "database": str(DB),
        "synthetic": True,
        "business_records": meaningful,
        "business_tables": list(BUSINESS_TABLES),
        "all_rows": sum(counts.values()),
        "table_counts": counts,
        "integrity": checks,
        "foreign_key_violations": foreign_keys,
        "statuses": {
            table: {
                row[0]: row[1]
                for row in conn.execute(
                    f'SELECT status,COUNT(*) FROM "{table}" GROUP BY status'
                )
            }
            for table in (
                "memberships",
                "payments",
                "tickets",
                "merch_orders",
                "expenses",
            )
        },
    }


def maintain_dataset(conn, students, *, settle):
    """Maintain only new dataset users, never sweep existing users' purchases.

    This intentionally scopes the normal expiry guards and settlement journal
    helper. Calling the application's global sweeps would affect old demo data.
    """
    from clubledger.core import clock
    from clubledger.payments.service import _post_settlement
    from clubledger.store.service import cancel_order

    placeholders = ",".join("?" for _ in students)
    now = clock.now()
    conn.execute(
        f"UPDATE ticket_holds SET status='EXPIRED' WHERE user_id IN ({placeholders}) AND status='HELD' AND expires_at<=?",
        (*students, now),
    )
    orders = conn.execute(
        f"SELECT id,user_id FROM merch_orders WHERE user_id IN ({placeholders}) AND status='RESERVED' AND expires_at<=?",
        (*students, now),
    ).fetchall()
    for order in orders:
        cancel_order(conn, None, order["id"], order["user_id"])
        conn.execute(
            "UPDATE merch_orders SET status='EXPIRED' WHERE id=? AND status='CANCELLED'",
            (order["id"],),
        )
    cutoff = (
        datetime.fromisoformat(now.replace("Z", "+00:00")) - timedelta(minutes=30)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    pending = conn.execute(
        f"SELECT id,ref_table,ref_id FROM payments WHERE user_id IN ({placeholders}) AND status IN ('CREATED','PENDING') AND created_at<=?",
        (*students, cutoff),
    ).fetchall()
    for payment in pending:
        conn.execute(
            "UPDATE payments SET status='EXPIRED' WHERE id=?", (payment["id"],)
        )
        if payment["ref_table"] == "memberships":
            conn.execute(
                "UPDATE memberships SET status='CANCELLED' WHERE id=? AND status='PENDING'",
                (payment["ref_id"],),
            )
    if settle:
        cutoff = (
            datetime.fromisoformat(now.replace("Z", "+00:00")) - timedelta(days=1)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        payments = conn.execute(
            f"SELECT id,amount_paise FROM payments WHERE user_id IN ({placeholders}) AND status='SUCCEEDED' AND settled_at IS NULL AND succeeded_at<=?",
            (*students, cutoff),
        ).fetchall()
        for payment in payments:
            _post_settlement(
                conn, None, "payment", payment["id"], payment["amount_paise"]
            )
            conn.execute(
                "UPDATE payments SET settled_at=? WHERE id=?", (now, payment["id"])
            )


def populate(conn, *, additive=False):
    from clubledger.core import clock
    from clubledger.core.auth import hash_password
    from clubledger.core.types import CartItem
    from clubledger.seed import seed_all
    from clubledger.wiring import build_handlers
    from clubledger.membership.service import start_join
    from clubledger.events.service import create_hold, check_in, expire_holds
    from clubledger.store.service import reserve_cart, mark_picked_up, expire_orders
    from clubledger.payments.simulator import dispatch_simulated_outcome
    from clubledger.payments.service import (
        refund_payment,
        settle_payments,
        expire_payments,
    )
    from clubledger.tasks.service import create_fundraiser, create_task
    from clubledger.comms.service import (
        create_announcement,
        publish,
        subscribe,
        process_mail_outbox,
    )
    from clubledger.expenses.service import (
        submit_expense,
        attach_receipt,
        approve_expense,
        pay_expense,
        reject_expense,
    )

    base = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=2)

    def at(delta):
        instant = (base + delta).strftime("%Y-%m-%dT%H:%M:%SZ")
        if os.environ.get("CLUBLEDGER_ENV") == "test":
            clock.set_now(instant)
        else:
            os.environ["CLUBLEDGER_DEMO_TIME"] = instant

    at(timedelta())
    if not additive:
        seed_all(conn, demo=True)
    now = clock.now()
    actors = {
        row["email"].split("@")[0]: row["id"]
        for row in conn.execute(
            "SELECT id,email FROM users WHERE email LIKE '%@skyline.edu'"
        )
    }
    term = conn.execute("SELECT id FROM terms WHERE status='OPEN'").fetchone()[0]
    password = hash_password("DemoPassword123!")
    first = [
        "Aarav",
        "Diya",
        "Kabir",
        "Meera",
        "Rohan",
        "Ananya",
        "Vihaan",
        "Isha",
        "Arjun",
        "Tara",
    ]
    last = ["Sharma", "Rao", "Patel", "Das", "Nair", "Joshi"]
    students = [] if additive else [actors["student"]]
    for index in range(0 if additive else 1, 60):
        students.append(
            conn.execute(
                "INSERT INTO users(email,name,password_hash,is_active,created_at) VALUES(?,?,?,1,?)",
                (
                    f"dataset{index:02d}@demo.example"
                    if additive
                    else f"student{index:02d}@demo.example",
                    f"{first[index % 10]} {last[index // 10]} (Demo {index:02d})",
                    password,
                    now,
                ),
            ).lastrowid
        )
    handlers = build_handlers()
    plan = conn.execute(
        "SELECT id FROM membership_plans ORDER BY id LIMIT 1"
    ).fetchone()[0]

    def outcome(payment, value="success"):
        return dispatch_simulated_outcome(
            conn, handlers, payment, value, "isolated-local-synthetic-demo-only"
        )

    # Thirty active memberships and five failed applications exercise both tiers.
    for index in range(35):
        payment = start_join(conn, students[index], plan, f"large-dues-{index}")
        outcome(payment, "success" if index < 30 else "fail")

    titles = [
        "Campus Music Night",
        "Innovation Showcase",
        "Spring Cultural Fest",
        "Photography Walk",
        "Design Sprint",
        "Debate Championship",
        "Alumni Networking",
        "Open Mic Evening",
        "Sustainability Workshop",
    ]
    events = [
        conn.execute(
            "SELECT id FROM events WHERE title='Spring Gala 2027' AND status='ON_SALE'"
        ).fetchone()[0]
    ]
    for index, title in enumerate(titles):
        start = (base + timedelta(days=10 + index * 3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = (base + timedelta(days=10 + index * 3, hours=3)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        events.append(
            conn.execute(
                "INSERT INTO events(term_id,title,venue,starts_at,ends_at,capacity,member_price_paise,public_price_paise,status,created_at) VALUES(?,?,?,?,?,100,?,?,'ON_SALE',?)",
                (
                    term,
                    title,
                    ["Grand Auditorium", "Student Centre", "Campus Lawn"][index % 3],
                    start,
                    end,
                    40000 + index * 4000,
                    50000 + index * 5000,
                    now,
                ),
            ).lastrowid
        )
    # Real paid tickets, including five refunds and ten admissions.
    for index in range(60):
        hold, payment = create_hold(
            conn, students[index], events[index % 10], 1, f"large-ticket-{index}"
        )
        outcome(payment)
        ticket = conn.execute(
            "SELECT * FROM tickets WHERE hold_id=?", (hold.id,)
        ).fetchone()
        if index < 5:
            refund_payment(conn, handlers, payment.id, actors["treasurer"])
        elif index < 15:
            assert (
                check_in(
                    conn, ticket["event_id"], ticket["code"], actors["events"]
                ).status
                == "OK"
            )
    for index in range(15):
        _, payment = create_hold(
            conn, students[index], events[index % 10], 1, f"large-unpaid-ticket-{index}"
        )
        if index < 10:
            outcome(payment, "fail")

    # Settle the older receipts through the genuine T+1 settlement service.
    at(timedelta(days=1))
    if additive:
        maintain_dataset(conn, students, settle=True)
    else:
        expire_holds(conn, clock.now())
        expire_payments(conn, clock.now())
        settle_payments(conn, clock.now())
    products = [
        "Campus hoodie",
        "Club notebook",
        "Reusable water bottle",
        "Enamel club pin",
        "Sports cap",
        "Campus lanyard",
        "Art print",
        "Volunteer wristband",
    ]
    new_variants = []
    for index, name in enumerate(products):
        product = conn.execute(
            "INSERT INTO products(name,description,base_price_paise,created_at) VALUES(?,?,?,?)",
            (
                name,
                "Synthetic campus merchandise for the reviewer demo.",
                25000 + index * 5000,
                clock.now(),
            ),
        ).lastrowid
        new_variants.append(
            conn.execute(
                "INSERT INTO variants(product_id,sku,size,physical_qty,created_at) VALUES(?,?,?,?,?)",
                (product, f"DEMO-{index}", "One size", 40, clock.now()),
            ).lastrowid
        )
    variants = (
        new_variants
        if additive
        else [row[0] for row in conn.execute("SELECT id FROM variants ORDER BY id")]
    )
    for index in range(30):
        order, payment = reserve_cart(
            conn,
            students[index],
            [CartItem(variants[index % len(variants)], 1)],
            f"large-order-{index}",
        )
        if index < 20:
            outcome(payment)
            if index < 4:
                refund_payment(conn, handlers, payment.id, actors["treasurer"])
            elif index < 10:
                mark_picked_up(conn, order.id, actors["store"])
        elif index < 25:
            outcome(payment, "fail")
    at(timedelta(days=1, minutes=20))
    if additive:
        maintain_dataset(conn, students, settle=False)
    else:
        expire_orders(conn, clock.now())
        expire_payments(conn, clock.now())
    at(timedelta(days=2))
    for index in range(35, 40):
        start_join(conn, students[index], plan, f"large-dues-{index}")

    # Linked fundraisers, tasks, expenses and valid, clearly synthetic PDFs.
    new_fundraisers = []
    for title in (["Student wellbeing fund"] if additive else []) + [
        "Campus food bank",
        "Scholarship support",
        "Green campus drive",
        "Community arts fund",
    ]:
        new_fundraisers.append(
            create_fundraiser(
                conn, term_id=term, title=title, goal_paise=5000000, status="ACTIVE"
            )
        )
    fundraisers = (
        new_fundraisers
        if additive
        else [row[0] for row in conn.execute("SELECT id FROM fundraisers")]
    )
    new_tasks = []
    for index in range(18):
        new_tasks.append(
            create_task(
                conn,
                fundraiser_id=fundraisers[index % 5],
                title=f"{['Book venue', 'Recruit volunteers', 'Prepare posters', 'Track donations', 'Publish update'][index % 5]} - demo {index + 1}",
                owner_user_id=students[index],
                due_at=(base + timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                status=["TODO", "DOING", "DONE", "BLOCKED"][index % 4],
            )
        )
    tasks = (
        [
            conn.execute(
                "SELECT id,fundraiser_id FROM tasks WHERE id=?", (task,)
            ).fetchone()
            for task in new_tasks
        ]
        if additive
        else conn.execute("SELECT id,fundraiser_id FROM tasks ORDER BY id").fetchall()
    )
    category = conn.execute("SELECT id FROM accounts WHERE code='5000'").fetchone()[0]
    for index in range(15):
        amount = 15000 + index * 2500
        task = tasks[index]
        expense = submit_expense(
            conn,
            submitter_id=students[index],
            category_account_id=category,
            amount_paise=amount,
            description=f"Synthetic demo: {['Poster printing', 'Venue supplies', 'Volunteer refreshments'][index % 3]} {index + 1}",
            fundraiser_id=task["fundraiser_id"],
            task_id=task["id"],
        )
        attach_receipt(
            conn,
            expense_id=expense,
            uploader_id=students[index],
            file_content=receipt_pdf(index + 1, amount),
            original_filename=f"synthetic-receipt-{index + 1}.pdf",
            mime_type="application/pdf",
        )
        if index < 10:
            approve_expense(
                conn,
                expense_id=expense,
                approver_user_id=actors["treasurer"],
                decision_note="Synthetic demo approval",
            )
            if index < 7:
                pay_expense(conn, expense_id=expense, payer_user_id=actors["treasurer"])
        elif index < 12:
            reject_expense(
                conn,
                expense_id=expense,
                approver_user_id=actors["treasurer"],
                decision_note="Synthetic demo: missing supporting details",
            )
    for user in students[:10]:
        email = conn.execute("SELECT email FROM users WHERE id=?", (user,)).fetchone()[
            0
        ]
        subscribe(conn, email, user)
    for title in [
        "Music night bookings open",
        "Volunteer orientation",
        "Store pickup hours",
        "Workshop registration",
        "Library drive update",
        "Expense submission guide",
        "New member benefits",
        "Event check-in reminder",
        "Club week programme",
    ]:
        announcement = create_announcement(
            conn,
            actors["comms"],
            title,
            "Synthetic demo announcement. Visit the relevant module to explore the linked club workflows; no real email is sent.",
        )
        publish(conn, announcement)
    if not additive:
        process_mail_outbox(conn, limit=200)
    os.environ.pop("CLUBLEDGER_DEMO_TIME", None)
    if os.environ.get("CLUBLEDGER_ENV") == "test":
        clock.reset()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Read-only validation of the existing isolated dataset",
    )
    args = parser.parse_args()
    configure_local()
    from clubledger.core.db import apply_migrations, unit_of_work

    if args.verify:
        if not DB.exists():
            raise SystemExit("Create the isolated demo first.")
        import sqlite3

        with sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            result = report(conn)
    else:
        DEMO_DIR.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents accidental reset or duplicate seeding.
        try:
            with DB.open("xb"):
                pass
        except FileExistsError:
            raise SystemExit(
                "Demo database already exists; no changes made. Use --verify."
            ) from None
        with unit_of_work(str(DB)) as conn:
            apply_migrations(conn)
            populate(conn)
            result = report(conn)
        (DEMO_DIR / "manifest.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
