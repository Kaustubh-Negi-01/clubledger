# Start here: understand ClubLedger in ten minutes

ClubLedger helps a student association manage memberships, event tickets, merchandise, tasks, reimbursements and finances. It is one application: a Python backend serves HTML pages and reads/writes a local SQLite database.

## 1. The four main folders

```text
frontend/                 What the user sees
  templates/              HTML pages with Jinja placeholders
  static/                 CSS, JavaScript, illustrations and fonts
backend/                  What the application does
  clubledger/
    api/                  URLs and request/response handling
    security/             Authentication, permissions, CSRF and request protections
    core/                 Shared database, clock and pricing helpers
    notifications/        Account notices and read status
    payments/, events/…   Business rules for each feature
    presentation/         Page context and QR rendering helpers
database/                 Schema and local data
  migrations/             Numbered SQL files defining the schema
  runtime/                Private local SQLite files, secrets and receipts
config/                   Explanation of settings and integrations
.env.example              Shareable example configuration
.env                      Your local settings; ignored by Git
tests/                    Automated checks, separate from application code
docs/                     Architecture, file map and reviewer preparation
```

`.env` is a file, not a folder. API code belongs in the backend; secret API keys, when an integration actually exists, belong in local environment settings. Payments remain simulated; real email delivery is configured separately on the hosted app. There is no runtime AI API. See `EMAIL_DELIVERY.md` and `NOTIFICATIONS.md`.

## 2. Languages and tools

| Technology | Job in this project | Where to look |
| --- | --- | --- |
| Python 3.12 | Backend logic, services, tests and maintenance commands | `backend/`, `tests/` |
| FastAPI | Matches HTTP URLs to Python handlers and validates inputs | `backend/clubledger/api/`, `main.py` |
| Uvicorn | Runs the web server | `backend/clubledger/cli.py` |
| HTML | Page structure: headings, forms, buttons and tables | `frontend/templates/` |
| Jinja2 | Fills HTML with backend data and conditional content | `frontend/templates/`, backend presentation helpers |
| CSS | Appearance, spacing, responsive layout and animations | `frontend/static/*.css` |
| JavaScript | Mobile menu, browser confirmations, submission state and payment popup | `frontend/static/app.js` |
| SQL / SQLite | Tables, relationships, constraints and transactions | `database/migrations/`, `backend/clubledger/core/db.py` |
| pytest / HTTPx TestClient | Runs isolated service and HTTP workflow tests | `tests/` |
| Ruff | Formats Python and checks configured fatal code errors | `pyproject.toml` |
| python-dotenv | Reads optional root `.env` settings | `backend/clubledger/config.py` |
| qrcode / Pillow | Generates membership and ticket QR images | `backend/clubledger/presentation/qr.py` |
| Markdown | Human-readable project documentation | `README.md`, folder READMEs, `docs/` |

We do not use React, a separate Node frontend server, PostgreSQL, Supabase or an ORM in this version. Node is not required to run the app. HTMX is retained as a readable vendor asset but is not loaded by the current base page.

## 3. How a request works

```text
User opens a URL or submits a form
    → FastAPI middleware checks the request
    → An API route reads its inputs and checks access
    → A service enforces the feature's rules
    → SQLite reads data or commits a transaction
    → The route returns HTML, JSON or a redirect
    → The browser displays the response
```

A **GET** normally reads a page. A **POST** normally performs an action. A **PATCH** changes part of a resource. A **303 redirect** sends the browser to a GET page after a form submission so a page refresh does not resubmit that form.

The browser is not trusted to choose prices, grant permissions or mark payments successful. The server validates these actions.

## 4. Read these files in order

1. `frontend/templates/base.html`: find the shared navigation and `{% block content %}` placeholder.
2. `frontend/templates/dashboard.html`: see how the dashboard fills that placeholder.
3. `backend/clubledger/main.py`: find the middleware, static mount and registered routers.
4. `backend/clubledger/api/store.py`: follow a reservation form into its route.
5. `backend/clubledger/store/service.py`: see the stock, price and order rules.
6. `backend/clubledger/core/db.py`: understand the transaction that makes related writes atomic.
7. `database/migrations/0005_store.sql`: identify orders, products, variants and their constraints.
8. `tests/e2e/test_first_slice.py`: see a complete user journey verified automatically.

Use [FILE_GUIDE.md](FILE_GUIDE.md) to find every source file and its functions. Use [API_REFERENCE.md](API_REFERENCE.md) for the actual endpoint list.

## 5. What common code means

```python
@router.post("/some-action")
def handle_action(...):
    ...
```

The decorator associates a URL and HTTP method with a function. This example is illustrative; consult the API reference for real endpoints.

```python
with unit_of_work() as conn:
    ...
```

Everything inside this block uses one database transaction. Normal completion commits the changes; an exception rolls them back. `BEGIN IMMEDIATE` makes SQLite acquire the write lock before performing the work.

```python
conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```

The `?` is a SQL parameter. Values are supplied separately rather than concatenated into SQL text.

```jinja
{% if membership %}
    <p>Member code: {{ membership.member_code }}</p>
{% endif %}
```

Jinja displays this paragraph only when membership data exists. It escapes ordinary displayed values so a user's text cannot turn into executable HTML.

## 6. Important words

| Word | Meaning |
| --- | --- |
| Authentication | Proving which account is signed in |
| Authorization | Checking what that account may do |
| CSRF token | A value checked before accepting browser actions, blocking submissions from another website |
| Idempotency | Repeating the same request does not repeat its side effects |
| Hold/reservation | A temporary claim on seats or stock before payment completes |
| Fulfillment | Actually granting the membership, tickets or order after money is recorded |
| Webhook | A callback telling the app about a payment outcome |
| Ledger | A financial record based on accounts and journal entries |
| Debit/credit | The two sides of accounting; every posted entry must balance |
| Settlement | Moving received money from clearing to cash after the defined delay |
| Migration | A numbered SQL change to the database schema |
| Fixture | Test setup, such as a temporary database or logged-in user |

## 7. Boundaries of this prototype

Payments and email are simulated locally. The UI works with real SQLite records, not hardcoded dashboard totals. A passing test suite is evidence for tested behavior, not a guarantee that every written requirement is certified or that a judge will award 95+. The requirement tracker previously recorded 20/110 as implemented; this reorganization does not inflate it.
