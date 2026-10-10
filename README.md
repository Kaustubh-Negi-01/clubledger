# ClubLedger

A student association workspace for memberships, events, merchandise, tasks, expenses and financial records.

**New to the code? Start with [the beginner guide](docs/START_HERE.md).** Then open the [file-by-file map](docs/FILE_GUIDE.md) or [reviewer preparation notes](docs/REVIEWER_PREPARATION.md).

## Four main folders

| Folder | What belongs here |
| --- | --- |
| [frontend/](frontend/README.md) | HTML/Jinja pages, CSS, JavaScript, fonts and illustrations |
| [backend/](backend/README.md) | Python/FastAPI, HTTP API routes, security and business logic |
| [database/](database/README.md) | SQL migrations and ignored local database/receipt storage |
| [config/](config/README.md) | Environment settings and integration documentation |

`.env` is an ignored settings file in the repository root, not an API-code folder. `.env.example` documents the available settings. `tests/` contains automated checks; `docs/` explains the architecture.

## Run locally on Windows

Use Python 3.12. Run these commands from the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m clubledger.cli migrate
.\.venv\Scripts\python.exe -m clubledger.cli seed --demo
.\.venv\Scripts\python.exe -m clubledger.cli start
```

Open <http://127.0.0.1:8010/dashboard>. Do not overwrite your existing `.env` when updating an already configured checkout. Demo seed accounts include `student@skyline.edu`, `admin@skyline.edu`, `treasurer@skyline.edu` and `events@skyline.edu`, with password `DemoPassword123!`.

On macOS/Linux, use `python3.12 -m venv .venv`, `.venv/bin/python` for the Python commands and `cp .env.example .env` for initial configuration.

## Verify

```sh
python -m pytest -q
python -m ruff check backend tests
python -m tests.req_coverage --mode progress
```

Use your virtual environment's Python. The reorganized project passed 222 tests, with one existing Starlette/HTTPx deprecation warning. See `docs/REORGANIZATION.md` for verification details.

## Features and boundaries

The app covers membership cards and discounts, ticket reservations and admission, stock reservations and pickup, task boards, receipt-backed reimbursements, announcements, a double-entry journal, financial reports, semester snapshots and officer handover.

Payments and email are **local simulations**. There is no real card charge, email delivery service or runtime AI API. The requirement evidence tracker is separate from the passing test count: 20/110 requirements were marked implemented before reorganization, with final certification incomplete.

## Documentation

- [Beginner guide and technology glossary](docs/START_HERE.md)
- [Each file and its job](docs/FILE_GUIDE.md)
- [Actual HTTP endpoints](docs/API_REFERENCE.md)
- [Database structure](docs/DATABASE_STRUCTURE.md)
- [Reviewer questions and code walkthroughs](docs/REVIEWER_PREPARATION.md)
- [What moved and how it was verified](docs/REORGANIZATION.md)

Original planning documents (`CONTRACT.md`, `REQUIREMENTS.md`, `BUILD_ORDER.md`) remain under `docs/`; historical paths in them may refer to the old layout. The new file guide describes the actual folder layout.

## Assets

Campus illustrations are original. Space Grotesk is served locally under the SIL Open Font License in `frontend/static/fonts/OFL.txt`. HTMX vendor source and its license are kept in `frontend/static/vendor/`, but the current app does not load it.
