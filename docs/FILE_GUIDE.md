# File-by-file code map

This inventory is generated from the reorganized source. Read the folder README first, then use this map to locate a feature. Framework/library code in `.venv` is not application code.

## Backend

### `backend/clubledger/__init__.py`

Marks this folder as a Python package; it has no HTTP endpoint of its own.


### `backend/clubledger/api/__init__.py`

Marks this folder as a Python package; it has no HTTP endpoint of its own.


### `backend/clubledger/api/auth.py`

Receives registration, login, logout and account requests.

- `_get_client_ip`: See the route/service explanation and its callers.
- `get_register`: Handle GET /auth/register. Get register.
- `post_register`: Handle POST /auth/register. Post register.
- `get_login`: Handle GET /auth/login. Get login.
- `post_login`: Handle POST /auth/login. Post login.
- `post_logout`: Handle POST /auth/logout. Post logout.
- `get_me`: Handle GET /me. Get me.

### `backend/clubledger/api/events.py`

Serves event discovery, ticket booking, admission and event reports.

- `get_optional_session`: Resolve session if present, otherwise return None for public routes.
- `require_events_manage_or_finance_view`: Dependency: verify caller has events.manage or finance.view permission.
- `get_events_list`: Public listing of events on sale with available seats and prices.
- `get_event_detail`: Public event detail and booking form (shows server-computed tier for logged-in user).
- `post_event_hold`: Reserve tickets under a capacity hold; redirect to payment or directly to tickets if free.
- `get_ticket`: Render owned ticket with seat code and optional QR.
- `get_checkin`: Staff check-in form for scanning QR or entering manual ticket code.
- `post_checkin_scan`: Staff check-in verification.
- `get_admin_event_report`: Admin event financial and attendance report per CONTRACT §11, §12.

### `backend/clubledger/api/expenses.py`

Accepts expense forms, receipt uploads and officer decisions.

- `list_expenses`: Handle GET /expenses. List expenses.
- `post_create_expense`: Handle POST /expenses/new. Post create expense.
- `post_upload_receipt`: Handle POST /expenses/{expense_id}/receipt. Post upload receipt.
- `download_receipt`: Handle GET /receipts/{receipt_id}. Download receipt.
- `post_approve_expense`: Handle POST /admin/expenses/{expense_id}/approve. Post approve expense.
- `post_reject_expense`: Handle POST /admin/expenses/{expense_id}/reject. Post reject expense.
- `post_pay_expense`: Handle POST /admin/expenses/{expense_id}/pay. Post pay expense.

### `backend/clubledger/api/membership.py`

Serves joining, membership cards and officer membership verification.

- `get_join`: Render plan list and join form with server-issued idempotency key.
- `post_join`: Start join workflow and redirect to payment simulator.
- `get_member_card`: Display user's active membership card with member code and validity.
- `get_verify`: Render staff membership verification lookup form.
- `post_verify_lookup`: Lookup member by code or QR token (staff verification).

### `backend/clubledger/api/payments.py`

Serves checkout and handles simulator outcomes, verified callbacks and officer payment actions.

- `_get_client_ip`: See the route/service explanation and its callers.
- `get_handlers`: See the route/service explanation and its callers.
- `get_pay`: Render simulated payment checkout page per CONTRACT §5, §12.
- `post_pay_outcome`: Simulate payment outcome (server-side signed) per CONTRACT §5.
- `post_payment_webhook`: External-shaped payment webhook per CONTRACT §5.
- `get_admin_payments`: List payments with optional problem queue filtering per CONTRACT §3.1, §12.
- `post_admin_refund`: Issue a full refund for a payment per CONTRACT §8.
- `post_admin_fulfill`: Manually fulfill an unfulfilled obligation per CONTRACT §3.1.
- `post_admin_resolve_receipt`: Resolve an unapplied receipt event per CONTRACT §3.1.

### `backend/clubledger/api/reports.py`

Serves financial summaries, account entries and integrity results.

- `_get_open_term_id`: See the route/service explanation and its callers.
- `get_finance_dashboard`: Handle GET . Get finance dashboard.
- `get_account_drilldown`: Handle GET /accounts/{code}. Get account drilldown.
- `get_entry_drilldown`: Handle GET /entries/{entry_id}. Get entry drilldown.
- `get_integrity_page`: Handle GET /integrity. Get integrity page.

### `backend/clubledger/api/store.py`

Serves merchandise pages and handles reservations, cancellation and pickup.

- `get_optional_session`: Resolve session if present, otherwise return None for public routes.
- `require_store_manage_or_pickup`: Dependency: verify caller holds store.manage or store.pickup permission.
- `get_store_catalog`: Public catalog showing active products and available stock per size (STO-01).
- `get_product_detail`: Public product detail page.
- `post_store_reserve`: Reserve cart items and redirect to payment simulator (STO-02).
- `get_user_orders`: View logged-in user's merchandise orders.
- `post_cancel_order`: Cancel merchandise order by owner.
- `post_order_pickup`: Staff pickup confirmation reducing physical and reserved stock (STO-07).

### `backend/clubledger/api/tasks.py`

Exposes task status changes and a JSON board handler.

- `get_board`: Handle GET /fundraisers/{fundraiser_id}/board. Get board.
- `patch_task_status`: Handle PATCH /tasks/{task_id}/status. Patch task status.

### `backend/clubledger/api/workspace.py`

Serves dashboard and club operations including announcements, tasks, inventory, close and handover.

- `money`: Convert a positive rupee amount to exact integer paise; reject excess decimal places.
- `open_term`: Find the open financial period or report that the term is closed.
- `redirect`: Return a 303 redirect so the browser follows a form submission with a GET.
- `dashboard`: Handle GET /dashboard. Dashboard.
- `announcements`: Handle GET /announcements. Announcements.
- `announcement`: Handle GET /announcements/{announcement_id}. Announcement.
- `subscribe`: Handle POST /subscribe. Subscribe.
- `unsubscribe_page`: Handle GET /unsubscribe/{token}. Unsubscribe page.
- `unsubscribe`: Handle POST /unsubscribe/{token}. Unsubscribe.
- `manage_announcements`: Handle GET /admin/announcements. Manage announcements.
- `draft_announcement`: Handle POST /admin/announcements. Draft announcement.
- `publish`: Handle POST /admin/announcements/{announcement_id}/publish. Publish.
- `mail`: Handle GET /dev/mail. Mail.
- `process_mail`: Handle POST /dev/mail/process. Process mail.
- `renewal_reminders`: Handle POST /dev/mail/reminders. Renewal reminders.
- `fundraisers`: Handle GET /fundraisers. Fundraisers.
- `fundraiser_create`: Handle POST /fundraisers. Fundraiser create.
- `board`: Handle GET /fundraisers/{fundraiser_id}/board. Board.
- `task_create`: Handle POST /fundraisers/{fundraiser_id}/tasks. Task create.
- `task_status`: Handle POST /tasks/{task_id}/status. Task status.
- `expenses`: Handle GET /expenses. Expenses.
- `expense_new`: Handle GET /expenses/new. Expense new.
- `expense_submit`: Handle POST /expenses/submit. Expense submit.
- `checkin_events`: Handle GET /admin/checkin. Checkin events.
- `adjustments`: Handle GET /admin/adjustments. Adjustments.
- `adjustment`: Handle POST /admin/adjustments. Adjustment.
- `close_page`: Handle GET /admin/close. Close page.
- `close_period`: Handle POST /admin/close. Close period.
- `snapshot`: Handle GET /snapshots/{snapshot_id}. Snapshot.
- `settlement`: Handle POST /admin/settle. Settlement.
- `advance_demo`: Handle POST /dev/advance-day. Advance demo.
- `expiration`: Handle POST /admin/expire. Expiration.
- `handover_page`: Handle GET /admin/handover. Handover page.
- `handover`: Handle POST /admin/handover. Handover.
- `members`: Handle GET /admin/members. Members.
- `grant_role`: Handle POST /admin/users/{user_id}/role. Grant role.
- `user_status`: Handle POST /admin/users/{user_id}/status. User status.
- `events_admin`: Handle GET /admin/events. Events admin.
- `event_create`: Handle POST /admin/events. Event create.
- `event_cancel`: Handle POST /admin/events/{event_id}/cancel. Event cancel.
- `inventory`: Handle GET /admin/store. Inventory.
- `product_create`: Handle POST /admin/store/products. Product create.
- `restock`: Handle POST /admin/store/variants/{variant_id}/restock. Restock.

### `backend/clubledger/auth/__init__.py`

Marks this folder as a Python package; it has no HTTP endpoint of its own.


### `backend/clubledger/cli.py`

Turns terminal commands into migration, startup, settlement and maintenance operations.

- `parse_args`: See the route/service explanation and its callers.
- `handle_migrate`: See the route/service explanation and its callers.
- `handle_seed`: See the route/service explanation and its callers.
- `handle_start`: See the route/service explanation and its callers.
- `handle_settle`: See the route/service explanation and its callers.
- `handle_expire_holds`: See the route/service explanation and its callers.
- `handle_check_integrity`: See the route/service explanation and its callers.
- `main`: See the route/service explanation and its callers.

### `backend/clubledger/close/__init__.py`

Marks this folder as a Python package; it has no HTTP endpoint of its own.


### `backend/clubledger/close/service.py`

Checks readiness, archives a financial period and transfers officer roles.

- `checklist`: Evaluate whether payments, stock, expenses and accounting are ready for period close.
- `run_close`: Close a ready financial period, save its snapshot and open the next term in one transaction.
- `run_handover`: Record officer handover and transfer the selected roles under the handover rules.

### `backend/clubledger/comms/__init__.py`

Marks this folder as a Python package; it has no HTTP endpoint of its own.


### `backend/clubledger/comms/service.py`

Publishes announcements, respects subscriptions and captures queued mail locally.

- `subscribe`: Record a validated email subscription without undoing a previous unsubscribe.
- `unsubscribe`: Mark the subscription identified by its token as unsubscribed.
- `create_announcement`: Save an announcement draft belonging to its author and financial term.
- `publish`: Publish a draft and queue eligible subscriber messages with deduplication.
- `send_reminders`: Queue eligible membership renewal reminders once for each reminder identity.
- `_capture`: See the route/service explanation and its callers.
- `process_mail_outbox`: Recheck delivery eligibility, then capture or suppress queued messages locally.

### `backend/clubledger/config.py`

Reads local settings without storing private credentials in source code.

- `Config`: See the route/service explanation and its callers.
- `get_env`: See the route/service explanation and its callers.
- `get_db_path`: See the route/service explanation and its callers.
- `get_sim_secret`: See the route/service explanation and its callers.
- `validate_server_binding`: Validate binding rules per CONTRACT G10.
- `get_config`: See the route/service explanation and its callers.

### `backend/clubledger/core/__init__.py`

Marks this folder as a Python package; it has no HTTP endpoint of its own.


### `backend/clubledger/core/auth.py`

Checks passwords, manages login sessions and determines user permissions.

- `_parse_utc`: See the route/service explanation and its callers.
- `_format_utc`: See the route/service explanation and its callers.
- `hash_password`: Hash password with hashlib.scrypt using per-user salt.
- `verify_password`: Verify password against stored scrypt hash.
- `register_user`: Register a new user. Raises DomainError('VALIDATION', 422) if duplicate email.
- `authenticate_user`: Authenticate user with email and password. Returns user_id if valid.
- `deactivate_user`: Deactivate a user and revoke all their sessions in the same transaction (AUTH-06).
- `create_session`: Create a new session row. Returns (raw_token, csrf_token).
- `load_session`: Validate and load session. Slides idle expiry if active (CONTRACT §4.1).
- `revoke_session`: Revoke a session server-side.
- `verify_csrf`: Verify CSRF token for authenticated session.
- `get_user_permissions`: Resolve live permissions from the database. Admin role grants all permissions.
- `get_current_session`: Dependency: resolve authenticated session from cl_session cookie.
- `require_perm`: FastAPI Depends factory: verify current session holds the required live permission.

### `backend/clubledger/core/clock.py`

Provides one clock for production, development demonstrations and tests.

- `now`: Return the current UTC timestamp formatted as YYYY-MM-DDTHH:MM:SSZ.
- `set_now`: Inject a deterministic timestamp.
- `reset`: Reset the injected clock back to wall time.
- `advance_demo_day`: See the route/service explanation and its callers.
- `_parse_demo`: See the route/service explanation and its callers.
- `academic_year_bounds`: Compute (label, starts_at_utc, expires_at_utc) in Asia/Kolkata (+05:30).

### `backend/clubledger/core/csrf.py`

Prevents another website from submitting an action using a logged-in user session.

- `verify_csrf_token`: Verify session CSRF token with constant-time comparison.
- `get_pre_session_csrf`: Retrieve pre-session CSRF token from request cookies.
- `ensure_pre_session_csrf`: Retrieve or generate a pre-session CSRF token and set it in the response cookie.
- `verify_pre_session_csrf`: Verify double-submit pre-session CSRF token.

### `backend/clubledger/core/db.py`

Opens SQLite safely and groups related writes into all-or-nothing transactions.

- `connect`: Connect to SQLite with pragmas per CONTRACT G6.
- `unit_of_work`: Single outer transaction context manager per CONTRACT G5 and §13.
- `split_sql_statements`: Split SQL script into executable statements without using sqlite3.executescript.
- `calculate_checksum`: Calculate SHA-256 checksum of SQL content.
- `_get_default_migrations_dir`: See the route/service explanation and its callers.
- `get_available_migrations`: Return sorted list of (number, filename, path) for valid migrations.
- `apply_migrations`: Apply migrations to database.

### `backend/clubledger/core/errors.py`

Names expected failures so routes can return clear errors without leaking internals.

- `DomainError`: Domain error representing an application-level failure (CONTRACT G8).
- `MigrationError`: Base error for migration failure.
- `MigrationGapError`: Raised when an internal migration gap is detected.
- `MigrationDuplicateError`: Raised when duplicate migration numbers are detected.
- `MigrationChecksumError`: Raised when an applied migration has a modified checksum.

### `backend/clubledger/core/idgen.py`

Creates unpredictable public IDs and tokens; hashes tokens for storage.

- `generate_token`: Generate a cryptographically secure random hex token.
- `hash_token`: Compute SHA-256 hex digest of a token.
- `generate_csrf_token`: Generate a CSRF token.
- `generate_idempotency_key`: Generate a UUID4 string for idempotency keys.
- `generate_public_id`: Generate an opaque public ID.

### `backend/clubledger/core/pricing.py`

Calculates eligible membership discounts using server-side data.

- `active_membership`: Resolve active membership covering instant 'at' per CONTRACT §2.
- `ticket_price`: Calculate server-authoritative ticket price per CONTRACT §2.
- `merch_price`: Calculate server-authoritative merchandise unit price per CONTRACT §2.

### `backend/clubledger/core/ratelimit.py`

Limits repeated requests such as login attempts and invalid webhooks.

- `_get_current_dt`: See the route/service explanation and its callers.
- `check_rate_limit`: Check and record a rate limit attempt.
- `enforce_rate_limit`: Check rate limit and raise DomainError('RATE_LIMITED', 429) if exceeded.
- `reset_rate_limits`: Reset all in-memory rate limit buckets (useful for test fixtures).

### `backend/clubledger/core/types.py`

Defines shared data shapes used when services call one another.

- `Payment`: See the route/service explanation and its callers.
- `FulfillResult`: See the route/service explanation and its callers.
- `EventOutcome`: See the route/service explanation and its callers.
- `Line`: See the route/service explanation and its callers.
- `Fulfiller`: See the route/service explanation and its callers.
- `RefundCheck`: See the route/service explanation and its callers.
- `RefundApply`: See the route/service explanation and its callers.
- `PurposeHandler`: See the route/service explanation and its callers.
- `Session`: See the route/service explanation and its callers.
- `Membership`: See the route/service explanation and its callers.
- `MemberCheck`: See the route/service explanation and its callers.
- `TicketHold`: See the route/service explanation and its callers.
- `Ticket`: See the route/service explanation and its callers.
- `CartItem`: See the route/service explanation and its callers.
- `MerchOrder`: See the route/service explanation and its callers.
- `CheckInResult`: See the route/service explanation and its callers.
- `CancelSummary`: See the route/service explanation and its callers.
- `EventReport`: See the route/service explanation and its callers.
- `Movement`: See the route/service explanation and its callers.
- `CashSummary`: See the route/service explanation and its callers.
- `IncomeExpense`: See the route/service explanation and its callers.
- `DrillDown`: See the route/service explanation and its callers.
- `Subscriber`: See the route/service explanation and its callers.
- `Services`: See the route/service explanation and its callers.

### `backend/clubledger/events/__init__.py`

Marks this folder as a Python package; it has no HTTP endpoint of its own.


### `backend/clubledger/events/service.py`

Reserves event capacity, issues tickets, checks admission and processes cancellation.

- `DependencyBlockerError`: Raised when an A-owned or D-owned dependency is not yet implemented.
- `seed_events`: Seed demo events per CONTRACT defaults.
- `_compute_ticket_price_fallback`: Fallback price calculation adhering strictly to CONTRACT §2 if pricing module is not loaded.
- `get_available_seats`: Calculate available seats per CONTRACT §1.4: capacity - (HELD with expires_at > now + ISSUED/USED tickets).
- `create_hold`: Create a capacity-safe hold or issue free tickets per CONTRACT §1.4, §2, §6, §13.3.
- `fulfill_ticket_hold`: Fulfill ticket hold transitioning HELD -> CONSUMED and generating N tickets per CONTRACT §1.4.
- `check_refundable_tickets`: Verify tickets can be refunded per CONTRACT §1.4 and §3.3.
- `apply_refund_tickets`: Transition tickets to REFUNDED per CONTRACT §3.3.
- `expire_holds`: Expire holds exceeding their TTL per CONTRACT §1.4.
- `check_in`: Staff check-in for ticket code per CONTRACT §1.4 and EVT-07.
- `cancel_event`: Cancel event: void free tickets, refund eligible paid tickets through refund_payment per CONTRACT §3.3.
- `event_report`: Generate event report per CONTRACT §1.4, §11, EVT-09.

### `backend/clubledger/expenses/__init__.py`

Marks this folder as a Python package; it has no HTTP endpoint of its own.


### `backend/clubledger/expenses/receipts.py`

Validates receipt bytes and stores uploads outside the public static directory.

- `get_receipts_storage_dir`: Resolve receipts storage directory safely.
- `validate_and_save_receipt`: Validate content, sniff magic bytes, and store securely.
- `resolve_receipt_file`: Resolve stored receipt path ensuring it stays inside the storage dir.

### `backend/clubledger/expenses/service.py`

Controls expense submission, approval and reimbursement journal entries.

- `_get_open_term_id`: See the route/service explanation and its callers.
- `submit_expense`: Submit a new expense (EXP-01).
- `attach_receipt`: Attach a receipt to an existing expense (EXP-02, EXP-03).
- `approve_expense`: Approve an expense (EXP-04).
- `reject_expense`: Reject an expense (EXP-04). Approver cannot be submitter.
- `pay_expense`: Pay (reimburse) an approved expense (EXP-05, EXP-06).
- `void_expense`: Void a SUBMITTED expense by submitter.
- `get_expense`: Get full expense detail with category code and attached receipts.

### `backend/clubledger/journal/__init__.py`

Marks this folder as a Python package; it has no HTTP endpoint of its own.


### `backend/clubledger/journal/service.py`

Posts balanced debit/credit entries and creates reversals instead of editing posted history.

- `_get_account_id`: See the route/service explanation and its callers.
- `_get_open_term_id`: See the route/service explanation and its callers.
- `_validate_paise`: Validate paise is a strict non-negative integer, rejecting bool/float/strings.
- `_extract_field`: Extract a field from dataclass, dict, sqlite3.Row, or generic object.
- `post_entry`: Post a balanced journal entry idempotently.
- `reverse_entry`: Reverse an existing POSTED journal entry exactly once.
- `reverse_all_for_source`: Reverse every not-yet-reversed entry for a given source, newest first.
- `post_payment_received`: Post payment received entry (CONTRACT §7).
- `post_payment_late_fulfilled`: Post obligation fulfillment for late-fulfilled payment (CONTRACT §7).
- `post_receipt_event`: Post journal entry for unapplied receipt event (CONTRACT §3.1, §7).
- `post_settlement`: Post settlement entry for payment or payment_event (CONTRACT §7).
- `post_expense_approved`: Post approved expense entry (CONTRACT §7).
- `post_expense_paid`: Post paid expense entry (CONTRACT §7).

### `backend/clubledger/main.py`

Starts the web application, checks incoming requests, and connects URLs to handlers.

- `create_app`: Create and configure the FastAPI application.

### `backend/clubledger/membership/__init__.py`

Marks this folder as a Python package; it has no HTTP endpoint of its own.


### `backend/clubledger/membership/service.py`

Creates memberships and activates or verifies them under the club rules.

- `DependencyBlockerError`: Raised when an A-owned or D-owned dependency is not yet implemented.
- `seed_plans`: Seed standard membership plans per CONTRACT defaults.
- `_parse_utc_iso`: Parse ISO UTC string ending with Z into datetime.
- `start_join`: Start join / renewal workflow creating PENDING membership and Payment per CONTRACT §1.3, §6, §13.3.
- `fulfill_dues`: Fulfill dues payment transitioning PENDING -> ACTIVE per CONTRACT §1.3 and §3.2.
- `check_refundable_dues`: Raise DomainError REFUND_BLOCKED if dues cannot be refunded per CONTRACT §13.1.
- `apply_refund_dues`: Transition ACTIVE/PENDING membership to REVOKED on refund per CONTRACT §3.2.
- `lookup_member`: Staff lookup of membership by member_code or qr_token per CONTRACT §1.3, §13.3.
- `enqueue_renewal_reminders`: Mark expired memberships and queue reminders per CONTRACT §1.3.

### `backend/clubledger/paths.py`

Finds the frontend and migration files in both local and installed copies.


### `backend/clubledger/payments/__init__.py`

Marks this folder as a Python package; it has no HTTP endpoint of its own.


### `backend/clubledger/payments/service.py`

Records money received, fulfillment, refunds, unresolved receipts and settlement.

- `_get_journal_service`: See the route/service explanation and its callers.
- `_post_payment_received`: See the route/service explanation and its callers.
- `_post_payment_late_fulfilled`: See the route/service explanation and its callers.
- `_post_receipt_event`: See the route/service explanation and its callers.
- `_post_settlement`: See the route/service explanation and its callers.
- `_reverse_all_for_source`: See the route/service explanation and its callers.
- `create_payment`: Create a new payment row per CONTRACT §1.2 and §13.3.
- `handle_event`: Trusted phase of event processing per CONTRACT §3.1, §5, §13.3.
- `refund_payment`: Issue a full refund for a SUCCEEDED payment per CONTRACT §8.
- `resolve_unfulfilled`: Resolve an unfulfilled payment obligation per CONTRACT §3.1.
- `resolve_receipt`: Resolve an unapplied receipt event per CONTRACT §3.1.
- `settle_payments`: Settle all SUCCEEDED payments and UNAPPLIED_RECEIPT events >= 1 day old per CONTRACT §7, §14.
- `expire_payments`: Expire CREATED/PENDING payments created > 30 minutes ago per CONTRACT §3.1, §14.

### `backend/clubledger/payments/simulator.py`

Creates signed local payment outcomes; it never calls a real bank.

- `create_simulator_payload`: Build simulator event payload per CONTRACT §5.
- `sign_simulator_payload`: Sign simulator payload server-side. Returns (raw_body_bytes, signature_header).
- `dispatch_simulated_outcome`: Build, server-side sign, and process a simulated payment outcome.

### `backend/clubledger/payments/webhook.py`

Checks the callback signature and payload before any database write.

- `parse_signature_header`: Parse 'X-Signature: t=<unix>,v1=<hex>' header.
- `verify_webhook_request`: Untrusted phase of webhook processing per CONTRACT §5.

### `backend/clubledger/presentation/__init__.py`

Marks this folder as a Python package; it has no HTTP endpoint of its own.


### `backend/clubledger/presentation/navigation.py`

Defines the sidebar links in one readable list; permissions decide which links appear.


### `backend/clubledger/presentation/qr.py`

Creates QR image data for membership verification and ticket admission.

- `image_data`: See the route/service explanation and its callers.

### `backend/clubledger/presentation/ui.py`

Loads the current user and permissions and renders shared Jinja page context.

- `viewer`: Read the current account and permissions for the shared page layout.
- `render`: Fill an HTML template with the supplied data and return the rendered page.

### `backend/clubledger/reports/__init__.py`

Marks this folder as a Python package; it has no HTTP endpoint of its own.


### `backend/clubledger/reports/service.py`

Reads accounting and operational data to calculate summaries and detect inconsistencies.

- `balance`: Calculate cumulative balance for a balance-sheet account.
- `movement`: Calculate period movement (Σdebit and Σcredit of POSTED lines) in a specific term.
- `cash_summary`: Generate CashSummary report per CONTRACT §11.
- `income_expense`: Generate IncomeExpense report for a given term.
- `reconcile_payment_event_journal`: Calculate net 4100 journal credit and total ticket price separately for a payment.
- `drilldown`: Drilldown from totals -> account -> entry -> source document.
- `check_integrity`: Verify financial and journal integrity per CONTRACT §11.

### `backend/clubledger/seed.py`

Creates initial roles and permissions and, when requested, realistic demo records.

- `seed_roles_and_permissions`: Seed fixed permissions, roles, and role_permissions idempotently.
- `seed_open_term`: Ensure at least one valid OPEN term exists per CONTRACT §1.1.
- `seed_demo_actors`: Seed usable dev-only demo actors and roles idempotently without hardcoded production credentials.
- `seed_all`: Central idempotent seed entrypoint per CONTRACT §14.
- `seed_demo_content`: See the route/service explanation and its callers.

### `backend/clubledger/store/__init__.py`

Marks this folder as a Python package; it has no HTTP endpoint of its own.


### `backend/clubledger/store/service.py`

Reserves available stock, fulfills orders, releases expired reservations and records pickup.

- `DependencyBlockerError`: Raised when an A-owned or D-owned dependency is not yet implemented.
- `seed_store`: Seed demo merchandise products and variants per CONTRACT defaults.
- `_compute_merch_price_fallback`: Fallback merchandise price calculation strictly adhering to CONTRACT §2 floor math.
- `reserve_cart`: Atomically reserve a cart of merchandise items per CONTRACT §1.5, §13.3, STO-02.
- `fulfill_merch_order`: Fulfill merchandise order transitioning RESERVED -> PAID per CONTRACT §1.5, STO-05.
- `check_refundable_merch`: Verify merchandise order is eligible for refund per CONTRACT §1.5, STO-09.
- `apply_refund_merch`: Apply refund transitioning PAID -> REFUNDED and releasing reserved stock once (STO-09).
- `expire_orders`: Expire orders exceeding their TTL and release reserved stock once per CONTRACT §1.5, STO-06.
- `mark_picked_up`: Staff pickup decreases both physical_qty and reserved_qty per CONTRACT §1.5, STO-07.
- `cancel_order`: Cancel order: releases reserved stock if unpaid, or refunds via payment handler if paid.

### `backend/clubledger/tasks/__init__.py`

Marks this folder as a Python package; it has no HTTP endpoint of its own.


### `backend/clubledger/tasks/service.py`

Manages fundraisers, task ownership, progress and spending rollups.

- `create_fundraiser`: Create a new fundraiser under a term.
- `get_fundraiser`: Retrieve fundraiser details and total spend vs goal.
- `create_task`: Create a task for a fundraiser.
- `update_task_status`: Update task status. Task owner or staff with tasks.manage can update status.
- `get_fundraiser_board`: Get on-track board showing tasks, counts per status, and overdue count (TSK-02).

### `backend/clubledger/wiring.py`

Connects each payment purpose to its membership, ticket or merchandise handler.

- `_merch_unavailable_fulfill`: See the route/service explanation and its callers.
- `_merch_unavailable_check_refundable`: See the route/service explanation and its callers.
- `_merch_unavailable_apply_refund`: See the route/service explanation and its callers.
- `build_handlers`: Construct PurposeHandler mapping for DUES, TICKET, and MERCH without side-effects.
- `build_services`: Build Services container per CONTRACT §13.2.

## Frontend files

| File | Job |
| --- | --- |
| `frontend/__init__.py` | Folder guide or resource package marker. |
| `frontend/README.md` | Folder guide or resource package marker. |
| `frontend/static/app.css` | Shared colours, typography, components, responsive layouts and confetti rules. |
| `frontend/static/app.js` | Menu, confirmation, submit feedback, form helpers and payment result dialog behavior. |
| `frontend/static/campus-pass.svg` | Original decorative dashboard pass illustration. |
| `frontend/static/fonts/OFL.txt` | Font redistribution license. |
| `frontend/static/fonts/SpaceGrotesk-Variable.ttf` | Local font file; not executable application code. |
| `frontend/static/page-layouts.css` | External stylesheet containing extracted page-specific element styles. |
| `frontend/static/vendor/htmx.js` | Third-party HTMX library or its license; not loaded by the current application layout. |
| `frontend/static/vendor/htmx.LICENSE` | Third-party HTMX library or its license; not loaded by the current application layout. |
| `frontend/templates/adjustments.html` | Renders adjustments page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/announcements.html` | Renders announcements page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/auth/login.html` | Renders login page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/auth/me.html` | Renders me page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/auth/register.html` | Renders register page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/base.html` | Defines shared navigation, heading, footer and asset loading for all pages. |
| `frontend/templates/board.html` | Renders board page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/checkin_select.html` | Renders checkin select page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/close.html` | Renders close page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/dashboard.html` | Renders dashboard page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/error.html` | Renders error page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/events/checkin.html` | Renders checkin page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/events/detail.html` | Renders detail page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/events/list.html` | Renders list page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/events/report.html` | Renders report page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/events/ticket.html` | Renders ticket page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/expenses.html` | Renders expenses page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/finance/account.html` | Renders account page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/finance/entry.html` | Renders entry page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/finance/index.html` | Renders index page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/finance/integrity.html` | Renders integrity page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/fundraisers.html` | Renders fundraisers page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/handover.html` | Renders handover page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/inventory.html` | Renders inventory page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/mail.html` | Renders mail page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/manage_announcements.html` | Renders manage announcements page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/manage_events.html` | Renders manage events page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/members.html` | Renders members page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/membership/card.html` | Renders card page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/membership/join.html` | Renders join page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/membership/verify.html` | Renders verify page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/payments/admin_payments.html` | Renders admin payments page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/payments/pay.html` | Renders pay page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/payments/result.html` | Shows the actual payment result; successful fulfilled purchases enable confetti. |
| `frontend/templates/snapshot.html` | Renders snapshot page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/store/catalog.html` | Renders catalog page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/store/detail.html` | Renders detail page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/store/orders.html` | Renders orders page content; inherits the shared layout unless it is a reusable fragment. |
| `frontend/templates/unsubscribe.html` | Renders unsubscribe page content; inherits the shared layout unless it is a reusable fragment. |

## Tests

Each `tests/unit/<feature>/test_*.py` file checks the feature named by its folder and filename. `tests/e2e/` connects features in complete user journeys.

| File | Job |
| --- | --- |
| `tests/__init__.py` | Tests package for ClubLedger. (0 test functions; parametrization may run additional cases.) |
| `tests/conftest.py` | Pytest conftest and test outcome recorder plugin. (0 test functions; parametrization may run additional cases.) |
| `tests/e2e/test_complete_workspace.py` | Browser workflow and period lifecycle acceptance tests on real migrated databases. (13 test functions; parametrization may run additional cases.) |
| `tests/e2e/test_first_slice.py` | End-to-end integration and regression tests for ClubLedger vertical slices. (7 test functions; parametrization may run additional cases.) |
| `tests/e2e/test_local_hardening.py` | Failure recovery and basic rendered accessibility on actual application routes. (13 test functions; parametrization may run additional cases.) |
| `tests/e2e/test_payment_feedback.py` | Test payment feedback (2 test functions; parametrization may run additional cases.) |
| `tests/e2e/test_project_layout.py` | Verify resource moves still serve assets and keep code out of HTML attributes. (2 test functions; parametrization may run additional cases.) |
| `tests/factories.py` | Test entity factories. (0 test functions; parametrization may run additional cases.) |
| `tests/req_coverage.py` | Requirement status and test coverage tracker. (0 test functions; parametrization may run additional cases.) |
| `tests/test_req_coverage.py` | Unit tests for the requirements coverage checker (tests.req_coverage). (15 test functions; parametrization may run additional cases.) |
| `tests/unit/core/__init__.py` | Unit tests for core modules. (0 test functions; parametrization may run additional cases.) |
| `tests/unit/core/test_auth.py` | Tests for scrypt password hashing, session lifecycles, and live permissions. (6 test functions; parametrization may run additional cases.) |
| `tests/unit/core/test_auth_routes.py` | HTTP endpoint tests for authentication routes and middleware. (3 test functions; parametrization may run additional cases.) |
| `tests/unit/core/test_clock.py` | Tests for deterministic clock controls and academic year boundaries per CONTRACT G4, G9. (4 test functions; parametrization may run additional cases.) |
| `tests/unit/core/test_csrf.py` | Tests for CSRF verification per CONTRACT §4.2, AUTH-07. (2 test functions; parametrization may run additional cases.) |
| `tests/unit/core/test_db.py` | Tests for database connection pragmas, unit_of_work, commit, and rollback. (4 test functions; parametrization may run additional cases.) |
| `tests/unit/core/test_migrations.py` | Tests for migration runner: prefix rules, gap rejection, checksum mismatch, and schema constraints. (12 test functions; parametrization may run additional cases.) |
| `tests/unit/core/test_pricing.py` | Unit tests for pricing and entitlement rules per CONTRACT.md §2. (3 test functions; parametrization may run additional cases.) |
| `tests/unit/core/test_ratelimit.py` | Tests for clock-driven sliding window rate limiter per CONTRACT §4.4, AUTH-12. (1 test functions; parametrization may run additional cases.) |
| `tests/unit/events/test_events_routes.py` | Unit tests for events routes per CONTRACT.md §12. (12 test functions; parametrization may run additional cases.) |
| `tests/unit/events/test_events_schema.py` | Test events schema (5 test functions; parametrization may run additional cases.) |
| `tests/unit/events/test_events_service.py` | Unit tests for events and ticketing service per CONTRACT.md §1.4, §2, §3.3, §13.3. (15 test functions; parametrization may run additional cases.) |
| `tests/unit/expenses/test_expenses_service.py` | Unit tests for Expenses and Receipts service and routes (EXP-01..07). (4 test functions; parametrization may run additional cases.) |
| `tests/unit/journal/test_journal_service.py` | Unit tests for journal schema and journal/service.py. (13 test functions; parametrization may run additional cases.) |
| `tests/unit/membership/test_membership_routes.py` | Test membership routes (5 test functions; parametrization may run additional cases.) |
| `tests/unit/membership/test_membership_schema.py` | Test membership schema (5 test functions; parametrization may run additional cases.) |
| `tests/unit/membership/test_membership_service.py` | Test membership service (8 test functions; parametrization may run additional cases.) |
| `tests/unit/payments/test_payments_routes.py` | HTTP route tests for payment checkout, simulator, webhooks, and admin endpoints. (5 test functions; parametrization may run additional cases.) |
| `tests/unit/payments/test_payments_service.py` | Unit tests for payment lifecycle, fulfillment, journal orchestration, and refunds per CONTRACT §3.1, §5, §7, §8. (14 test functions; parametrization may run additional cases.) |
| `tests/unit/payments/test_simulator.py` | Unit tests for payment simulator signing and dispatch per CONTRACT §5. (2 test functions; parametrization may run additional cases.) |
| `tests/unit/payments/test_webhook.py` | Unit tests for untrusted webhook verification and rejection rules per CONTRACT §5. (8 test functions; parametrization may run additional cases.) |
| `tests/unit/reports/test_reports_routes.py` | Unit tests for finance reports routes (CONTRACT §12). (2 test functions; parametrization may run additional cases.) |
| `tests/unit/reports/test_reports_service.py` | Unit tests for reports domain service (CONTRACT §11). (4 test functions; parametrization may run additional cases.) |
| `tests/unit/store/test_store_routes.py` | Unit tests for store and merchandise routes per CONTRACT.md §12, STO-01 to STO-09. (11 test functions; parametrization may run additional cases.) |
| `tests/unit/store/test_store_schema.py` | Test store schema (5 test functions; parametrization may run additional cases.) |
| `tests/unit/store/test_store_service.py` | Unit tests for store and merchandise service per CONTRACT.md §1.5, §8, §13.3, STO-01 to STO-09. (17 test functions; parametrization may run additional cases.) |
| `tests/unit/tasks/test_tasks_service.py` | Unit tests for Tasks service and board (TSK-01..04). (1 test functions; parametrization may run additional cases.) |

## Other repository files

| Path | Job |
| --- | --- |
| `pyproject.toml` | Python dependency, packaging and formatting configuration |
| `pytest.ini` | Test discovery/import paths and requirement marker convention |
| `.github/workflows/ci.yml` | GitHub automation that installs and tests the application |
| `.gitignore` | Keeps runtime data, secrets, caches and virtual environments out of Git |
| `.env.example` | Safe configuration template; copy to `.env` for local settings |
| `.env` | Private local settings, ignored by Git |
| `docs/CONTRACT.md` | Original implementation rules; historical paths may use the earlier layout |
| `docs/REQUIREMENTS.md` | Requirement IDs and expected evidence |
| `docs/BUILD_ORDER.md` | Original team build plan; historical ownership and paths |
| `database/migrations/` | Numbered SQL schema definitions; see database README |
| `database/runtime/` | Local database, generated secret and receipts, excluded from commits |
| `.venv/` | Installed Python and third-party dependencies; do not edit library files |
| `*.egg-info/`, `.pytest_cache/`, `.ruff_cache/`, `__pycache__/` | Generated installation/test/compiler metadata, not source |

## Reading and configuration guides

| File | Job |
| --- | --- |
| `README.md` | Setup, startup and links to the beginner documentation. |
| `docs/START_HERE.md` | Architecture, technologies and how to read the code. |
| `docs/FILE_GUIDE.md` | Inventory of source files and their responsibilities. |
| `docs/API_REFERENCE.md` | Actual HTTP methods, URLs and handlers. |
| `docs/DATABASE_STRUCTURE.md` | SQLite tables, columns, constraints and triggers. |
| `docs/REVIEWER_PREPARATION.md` | Walkthroughs and factual answers for the reviewer. |
| `docs/REORGANIZATION.md` | Move map, verification and recovery information. |
| `backend/README.md` | Backend layers and request flow. |
| `frontend/README.md` | Templates, assets and frontend behavior. |
| `config/README.md` | Environment settings and integration boundaries. |
| `database/README.md` | Migrations versus runtime data. |
| `database/__init__.py` | Makes packaged migrations discoverable. |
| `tests/req_status.json` | Tracks requirement evidence; it is not application data. |

## Event ticket design additions

- `backend/clubledger/presentation/event_display.py`: formats stored UTC event timestamps for readable IST dates and times, including midnight rollover; does not change stored times or booking rules.
- `frontend/static/event-tickets.css`: responsive event poster, booking panel, admission-stub and print styles.
- `frontend/static/campus-gala.svg`: original decorative campus-gathering illustration, separate from the real QR code.

- `frontend/static/campus-paper-pattern.svg`: faint arch and botanical background for the parchment centre; decorative only.

## Ticket checkout design

- `frontend/templates/payments/ticket_checkout.html`: themed ticket checkout, using the saved payment and its owned reservation details; retains the existing CSRF and simulator form actions.
- `frontend/static/ticket-checkout.css`: parchment checkout layout and responsive styles; loaded only for ticket payments.
- `backend/clubledger/api/payments.py`: obtains optional event/quantity display information through the owned ticket hold; payment amount and status remain authoritative.

- `frontend/static/campus-string-lights.svg`: original overlapping warm festival-light strands across the top of the ticket checkout; no animation or payment logic.

- `frontend/static/checkout-line-art.svg`: decorative campus arches, flowing lines and botanicals with soft offset shadows behind checkout content.

## Cloud deployment additions

- `backend/server.py`: exports FastAPI for Vercel.
- `backend/clubledger/core/postgres.py`: Supabase connections, transactions, row compatibility and checked migrations.
- `database/postgres/`: PostgreSQL counterparts of SQLite migrations, plus persistent cloud receipt bytes and rate-limit attempts.
- `tests/cloud/`: isolated real PostgreSQL acceptance flows; skipped when the test credential is absent.
- `vercel.json`, `.python-version`, `.vercelignore`: cloud framework, region, runtime and upload exclusions.
- `docs/DEPLOYMENT.md`: hosting, credentials, receipt storage and release checks.
