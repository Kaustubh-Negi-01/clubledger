# Isolated reviewer demo dataset

This is one separate SQLite database with **266 meaningful business records**,
not 250 separate databases. Every person, receipt and transaction is synthetic.
It does not import, reset or change the ordinary preview database or Supabase.

## Where everything lives

| File or folder | Purpose |
|---|---|
| `scripts/create_large_demo.py` | Builds a new dataset through real membership, purchase, refund, settlement and expense services. Refuses to overwrite an existing dataset. |
| `scripts/start_large_demo.ps1` | Runs the existing app against this database on port 8011, forcing a local SQLite connection. |
| `runtime/large-demo/clubledger-large-demo.db` | Private, Git-ignored SQLite database. |
| `runtime/large-demo/receipts/` | Fifteen synthetic, viewable PDF receipts. |
| `runtime/large-demo/manifest.json` | Counts, statuses and integrity evidence at generation time. |

## Create, verify and run

Run from the repository root:

```powershell
.venv\Scripts\python.exe database/scripts/create_large_demo.py
.venv\Scripts\python.exe database/scripts/create_large_demo.py --verify
powershell -ExecutionPolicy Bypass -File database/scripts/start_large_demo.ps1
```

Open **http://127.0.0.1:8011**. Port 8010 remains the original preview.
If the dataset already exists, creation stops without modifying it. Verification
uses a read-only SQLite connection. There is no reset or cloud import command.

## Business records counted toward 250+

| Category | Count |
|---|---:|
| Users: 60 students, 6 other demonstration accounts | 66 |
| Membership applications | 40 |
| Events | 10 |
| Tickets | 60 |
| Products | 10 |
| Merchandise orders | 30 |
| Expenses | 15 |
| Fundraisers | 5 |
| Tasks | 20 |
| Announcements | 10 |
| **Meaningful total** | **266** |

Payments, journal lines, order items, variants, receipts, roles, sessions and
migration rows are additional supporting records; they do not inflate this total.
At generation: 1,760 total rows, 145 payments, 221 journal entries, 442 journal lines.
Counts can change when you operate the demo.

## Accounts and demonstrations

All these **local synthetic accounts** use `DemoPassword123!`:

| Account | What to demonstrate |
|---|---|
| `student@skyline.edu` | Active membership, member pricing, ticket refund and merchandise refund history. |
| `student06@demo.example` | Active member with a used ticket and picked-up order. |
| `student15@demo.example` | Active member with an issued ticket and paid order awaiting pickup. |
| `student30@demo.example` | Failed dues application: no active membership or member discount. |
| `student35@demo.example` | Pending dues application and membership checkout. |
| `admin@skyline.edu` | Full management views. |
| `treasurer@skyline.edu` | Payments, refunds, financial ledger and reimbursement decisions. |
| `events@skyline.edu` | Event management and ticket check-in. |
| `store@skyline.edu` | Stock and paid-order pickup. |
| `comms@skyline.edu` | Announcements and fundraiser tasks. |

Tickets include 45 issued, 10 used and 5 refunded. Orders include 10 paid,
6 picked up, 4 refunded, 5 failed/cancelled and 5 expired. Expenses include
7 paid, 3 approved, 2 rejected and 3 submitted. Memberships include 30 active,
5 failed/cancelled and 5 pending. Tasks demonstrate all four progress states.

Older payments were settled through the real T+1 service; newer merchandise
payments remain in clearing until the treasurer settles them. PDF receipts are
explicitly marked **SYNTHETIC / NOT A REAL PURCHASE**. Email is captured locally.
Pending checkouts may expire normally as time advances; this is a snapshot, not
a frozen clock or an automatic reset system.

## Validation

Creation must pass SQLite integrity, foreign keys and all eight application
integrity checks: balanced journals, received-payment entries, expense postings,
source links, required paid-expense receipts, ticket-to-journal reconciliation,
unapplied receipts and reserved-stock reconciliation. Creation is atomic for
database records. If creation fails, the existing-file guard deliberately stops
automatic retries so incomplete artifacts can be inspected rather than erased.

The dataset is for workflow demonstrations. It is not a load benchmark or proof
of performance at production scale. Creating the local dataset does not upload it.

## Explicit cloud append

`scripts/append_large_demo.py` exposes `append_dataset(conn)` for an authorized
operator using the configured connection inside `unit_of_work`. It never runs
at application startup, during deployment, or on a browser request. It adds
**254 new business records** to an already initialized database: 60 separate
students (`dataset00@demo.example` through `dataset59@demo.example`), 40
membership applications, 9 events, 60 tickets, 8 products, 30 orders, 15 expenses,
5 fundraisers, 18 tasks and 9 announcements. Password: `DemoPassword123!`.

The cloud dataset students use their own transaction namespace; original demo
accounts and transactions are preserved. Only the new students' purchases are
expired, settled or refunded during seeding. New PDF receipts use the backend's
private PostgreSQL receipt storage. Emails are queued, not delivered externally.

Before committing, the utility compares fingerprints of every existing durable
record and requires all integrity checks to pass. A transaction rollback handles
failure. A `demo.seed / large-demo-v1` completion marker makes repeated execution
a no-op. Take a private pre-seed snapshot before the first live invocation.
Dashboard totals and computed availability will naturally change with new data.

The fresh local dataset and additive cloud dataset differ slightly in counts,
because the cloud append preserves the existing demonstration records instead
of replacing them. Neither operation creates new schema objects or changes roles.

## Event presentation

`frontend/templates/events/themes.html` maps the nine demo event titles to unique
illustrations and palettes. `frontend/static/event-art/` holds the illustrations
and their shadowed line-art paper backgrounds. `frontend/static/event-themes.css`
applies the design to listings, ticket passes and checkout. The original Spring
Gala design is the unchanged fallback. These files do not control pricing,
payments, stock or admission; those remain in the backend services.
