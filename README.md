# ClubLedger

Single-club ledger and operational system for Skyline Student Association.

## Requirements
- Python 3.12+

## Setup Instructions

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -e ".[test]"
   ```

3. Run migrations:
   ```bash
   python -m clubledger.cli migrate
   ```

4. Seed and start the local demo:
   ```bash
   python -m clubledger.cli seed --demo
   python -m clubledger.cli start --host 127.0.0.1 --port 8010
   ```
   Open <http://127.0.0.1:8010/dashboard>. The default environment is `dev`.

5. Run the full test suite and checks from the repository root:
   ```bash
   python -m pytest -q
   python -m ruff check clubledger tests
   python -m tests.req_coverage --mode progress
   ```

## Demo accounts

Demo seed accounts use password `DemoPassword123!`:

| Account | Purpose |
| --- | --- |
| `student@skyline.edu` | Membership, events and merchandise |
| `admin@skyline.edu` | Full officer workspace |
| `treasurer@skyline.edu` | Financial operations |
| `events@skyline.edu` | Event management and admission |

Payment outcomes are simulated and email is captured locally; this demo does not charge cards or deliver external email. The development demo clock can demonstrate T+1 settlement. Advancing it can expire sessions.

SQLite data defaults to `data/clubledger.db`; use `CLUBLEDGER_DB_PATH` to select another database. Database contents and generated secrets are excluded from Git.

## Delivered workspace

- Responsive campus dashboard and permission-based navigation.
- Membership verification cards and server-authoritative member pricing.
- Ticket reservations, payment fulfillment, refunds and one-time admission.
- Merchandise reservations, expiry, refunds and officer pickup.
- Fundraiser task boards, receipt-backed expense approval and reimbursement.
- Announcements, subscriptions, reminders and local mail capture.
- Double-entry journal, financial reports, reconciliation and integrity checks.
- Semester-close checklist, immutable snapshots and officer handover.

The approved local version passed 217 tests on Python 3.12, with one Starlette/HTTPx deprecation warning. All 20 main navigation pages were checked at phone width without page-level horizontal overflow. Wide tables scroll within their own containers.

The requirement evidence tracker records 20 of 110 requirements as implemented. Progress mode permits planned requirements; final requirement certification and external evaluator scores remain incomplete. The documents under `docs/` describe intended requirements, not certification of every feature.

## Assets

Campus illustrations are original. Space Grotesk is hosted locally with its SIL Open Font License in `clubledger/web/static/fonts/OFL.txt`. Reference websites informed visual direction; their artwork and source code were not copied.
