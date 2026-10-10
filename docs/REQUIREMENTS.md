# ClubLedger Requirements and Test Map

Every requirement has an ID. Every ID maps to at least one positive (`+`) and one negative (`-`) planned test. Nothing here has been run; these are plans, not results.

## Test conventions

- `pytest.ini`: `markers = req(id): requirement ID from docs/REQUIREMENTS.md`, `addopts = --strict-markers`.
- Each test carries `@pytest.mark.req("MEM-03")` (one or more). A `conftest.py` hook in `tests/` (Owner D) collects markers and **fails the session if** a marker ID is not in this file, or an ID here has no test (check run by `python -m tests.req_coverage`).
- Test IDs are `tests/<area>/test_<file>.py::<name>`. Areas: `auth`, `payments`, `membership`, `events`, `store`, `journal`, `expenses`, `comms`, `tasks`, `close`, `e2e`, `a11y`.
- Owner D writes tests from this file independently of implementers (does not read service internals; uses HTTP routes and the CLI, plus DB reads for assertions). Services tests in the owners' areas are allowed but D's suite is the evidence of record.
- Time is controlled with `core.clock.set_now()`. Each test uses a fresh temp SQLite file and migrations.
- Evidence (`evidence/`): `pytest -q` output saved verbatim with date, git hash, and counts; `req_coverage` output; axe/manual a11y notes; screenshots. If something was not run, the file says "not run". No scores are invented.

## A. Auth, sessions, CSRF, permissions

| ID | Requirement | + Positive test | − Negative test |
|----|-------------|-----------------|-----------------|
| AUTH-01 | Registration creates a user with no membership benefits. | register → `/me` shows "not a member"; ticket price shown = public. | duplicate email (case-insensitive) → 422. |
| AUTH-02 | Passwords stored as scrypt hash; login verifies. | login ok sets HttpOnly cookie. | wrong password → 401, no session row. |
| AUTH-03 | Sessions expire (absolute 8 h, idle 2 h). | request at +1h59m works and refreshes. | request at +2h01m idle → 401; at +8h01m regardless of activity → 401. |
| AUTH-04 | Logout invalidates the session server-side. | logout → `revoked_at` set. | replaying the old cookie → 401. |
| AUTH-05 | Role revocation takes effect on the next request. | grant `door`, `/checkin` 200. | revoke role (cookie unchanged) → same cookie now 403. |
| AUTH-06 | Deactivating a user revokes their sessions. | deactivate → all session rows revoked. | old cookie → 401. |
| AUTH-07 | Browser mutations require CSRF. | POST with valid token succeeds. | missing/foreign-session token → 403 `CSRF_FAILED`, no mutation (checked for every POST route via route table sweep). |
| AUTH-08 | `/webhooks/payments` is the only CSRF exemption. | signed webhook without CSRF works. | route sweep: any other mutating route without CSRF returns 403; webhook with bad signature → 400. |
| AUTH-09 | Ownership: users access only their own payments/tickets/orders/receipts. | owner GET 200. | other user GET → 404 for `/tickets/{id}`, `/pay/{id}`, `/me/orders`, `/receipts/{id}`. |
| AUTH-10 | Permissions are explicit; `comms.mail_viewer` and `receipts.view_all` not implied. | `comms` role sees `/dev/mail`. | `events` and `door` roles → 403 on `/dev/mail`, others' receipts. |
| AUTH-11 | Purchases require login. | logged-in non-member can hold a ticket at public price. | anonymous POST hold/reserve/join → 401/redirect to login. |

## B. Payments

| ID | Requirement | + | − |
|----|-------------|---|---|
| PAY-01 | Money is integer paise; client cannot set amount. | hold response amount == server price. | POST with extra `amount`/`price` field is ignored (price unchanged). |
| PAY-02 | Webhook signature/timestamp validated before any mutation. | valid signature applies. | bad signature → 400; timestamp 6 min old → 400; DB unchanged both times. |
| PAY-03 | Event type, payment identity, currency, amount validated. | exact match applies. | wrong amount, currency `USD`, unknown payment id, wrong user id, unknown event type → MISMATCH/REJECTED; payment and fulfillment unchanged; no journal rows. |
| PAY-04 | Failed/pending events grant nothing. | `payment.failed` → FAILED. | no ticket/membership/order created; no journal entry; capacity still held until expiry. |
| PAY-05 | Duplicate `event_id` is a no-op. | second delivery returns 200 `IGNORED_DUP`. | tickets count and journal count unchanged after replay (×3). |
| PAY-06 | Simulator signs server-side. | browser outcome post succeeds. | response body and templates never contain the secret or a `v1=` signature; ownership check blocks other users. |
| PAY-07 | `FAILED` is terminal. | fail then new hold works. | success after failed → MISMATCH, no grant. |
| PAY-08 | Late success after hold expiry → UNFULFILLED obligation. | expire hold, then success: status SUCCEEDED, fulfillment UNFULFILLED, journal Dr1100/Cr2000. | no ticket issued; revenue (4100) unchanged; report shows obligation > 0. |
| PAY-09 | Staff can resolve an obligation: refund or manual fulfill. | refund: RESOLVED_REFUNDED, 2000 → 0. manual fulfill (seat free): tickets issued, Dr2000/Cr4100. | manual fulfill when event full → `SOLD_OUT`, obligation remains. |
| PAY-10 | One outer transaction; fulfillment and journal atomic. | success leaves ticket + 1 journal entry. | inject journal failure → rollback: no ticket, payment still PENDING, hold still HELD; retry with same event succeeds. |
| PAY-11 | No nested transactions. | static test greps services for `BEGIN`/`COMMIT`/`ROLLBACK` (only `core/db.py` allowed). | adding a nested `BEGIN` in a fixture raises; services receive an in-transaction conn (`conn.in_transaction` True). |
| PAY-12 | Full refunds only. | refund restores everything per type. | no partial amount accepted (422 on `amount` param); refund of REFUNDED/FAILED → 409. |
| PAY-13 | Refund rejected after use/pickup. | unused ticket refund ok. | ticket USED → `REFUND_BLOCKED`; merch PICKED_UP → `REFUND_BLOCKED`; nothing changes. |
| PAY-14 | Dues refund revokes entitlement. | membership REVOKED; next ticket price = public. | check-in/verify shows not a member. |
| PAY-15 | Settlement/cash treatment. | before `settle`: cash 0, clearing = X; after `settle`: cash X, clearing 0. | second `settle` run posts nothing (idempotent). refund before/after settle credits 1100/1000 respectively. |
| PAY-16 | Idempotent journal effects. | each of received/settled/refunded exists once per payment. | replaying handler functions directly does not duplicate (unique key). |

## C. Membership

| ID | Requirement | + | − |
|----|-------------|---|---|
| MEM-01 | Join creates PENDING membership + payment at plan price. | amount == plan dues. | PENDING gives no discount and `verify` shows not active. |
| MEM-02 | Dues success activates membership; sets `expires_on = term end`, `member_code`, `qr_token`. | fields set. | dues failure → stays PENDING. |
| MEM-03 | Benefits: discounted ticket and merch price for ACTIVE only. | member price on ticket + merch. | PENDING/EXPIRED/REVOKED/non-member pay public price. |
| MEM-04 | No duplicate live membership per user per term. | renewal in next term allowed (≥30 d before expiry). | second join in same term → `ALREADY_MEMBER`. |
| MEM-05 | Annual expiry. | at `expires_on` boundary membership is inactive; `send-reminders` flips status to EXPIRED. | one second before boundary still active. |
| MEM-06 | Renewal reminders at 30 d and 7 d and expiry day, once each. | clock at T−30d: 1 mail queued (`process-mail` → captured). | rerun same day → no new mail; user with no email/inactive skipped; non-members never mailed. |
| MEM-07 | Staff verification by code or QR. | `verifier` role sees name + ACTIVE. | no role → 403; unknown code → "not found"; expired → "EXPIRED"; page doesn't expose email/payment info. |
| MEM-08 | Price tier frozen at hold time. | membership bought after hold does not reprice that hold. | membership revoked after hold does not reprice either. |

## D. Events and tickets

| ID | Requirement | + | − |
|----|-------------|---|---|
| EVT-01 | Events list shows member and public prices and seats left. | values match DB. | DRAFT events hidden from public. |
| EVT-02 | Member vs public ticket price chosen server-side. | member pays member price. | non-member pays public; forged `price_tier` field ignored. |
| EVT-03 | Capacity reservation counts HELD + ISSUED + USED. | capacity 2: hold 2 ok. | third hold → `SOLD_OUT`; concurrent holds (two threads, one seat) → exactly one succeeds. |
| EVT-04 | Hold TTL and expiry release capacity once. | `expire-holds` after TTL frees seats. | running it twice does not free twice (capacity never exceeds `capacity`); expired hold can't be paid into tickets (→ PAY-08). |
| EVT-05 | Hold consumption releases held capacity exactly once. | after fulfillment: held=0, tickets=qty, available = cap − qty. | double fulfillment attempt → second raises/no-op; tickets still qty (UNIQUE hold_id). |
| EVT-06 | One ticket per seat with unique opaque code. | qty 3 → 3 codes. | codes not guessable/sequential; qty 0 or 11 → 422; qty > `max_per_order` → 422. |
| EVT-07 | Check-in by QR text or manual code. | first scan → USED, `used_at`, `used_by`. | second scan → `ALREADY_USED` (shows first time); unknown code → not found; other event's ticket → rejected; REFUNDED ticket → rejected. |
| EVT-08 | Check-in is staff-only. | `door` role 200. | member/anonymous → 403/401. |
| EVT-09 | Attendance and proceeds report. | sold, attended, no_shows, proceeds correct on a fixture of mixed tier/refund. | proceeds exclude refunded and unfulfilled; journal total for event equals report. |
| EVT-10 | Free ticket (price 0) needs no payment. | ticket issued immediately; no journal. | still consumes capacity and requires login. |
| EVT-11 | Event cancel → tickets VOID + refund path. | each VOID ticket's payment refundable. | USED tickets not refunded automatically (flagged). |

## E. Store

| ID | Requirement | + | − |
|----|-------------|---|---|
| STO-01 | Variants with per-size stock. | listing shows sizes with counts. | out-of-stock size disabled; inactive product hidden. |
| STO-02 | Cart reservation is atomic. | cart of 3 lines reserves all, stock decremented. | one line short → `INSUFFICIENT_STOCK`, **no** line decremented. |
| STO-03 | Quantity validation. | qty 1–10 accepted. | 0, negative, 11, non-int, duplicate variant lines → 422. |
| STO-04 | Server-authoritative merch price with member discount. | member discounted (floor math). | forged price ignored; total == Σ(unit×qty). |
| STO-05 | Payment success → PAID. | order PAID, one journal entry 4200. | failure/expiry restores stock exactly once. |
| STO-06 | Reservation expiry restores stock once. | after TTL stock back. | rerun doesn't double-restore; late success → UNFULFILLED (PAY-08 pattern). |
| STO-07 | Pickup by staff. | PAID → PICKED_UP. | unpaid/RESERVED → 409; non-staff → 403; second pickup → 409. |
| STO-08 | Oversell race. | two concurrent carts for last unit: one wins. | stock never negative (CHECK constraint hit would fail test). |
| STO-09 | Refund pre-pickup restores stock. | stock +qty, order REFUNDED. | after pickup → `REFUND_BLOCKED`. |

## F. Journal and reports

| ID | Requirement | + | − |
|----|-------------|---|---|
| JNL-01 | Posted entries balance. | `post_entry` balanced posts. | unbalanced → error; trigger also aborts direct SQL status flip on unbalanced entry; single-line entry rejected. |
| JNL-02 | Posted entries immutable. | read OK. | INSERT/UPDATE/DELETE on lines of POSTED entry → ABORT; UPDATE/DELETE of posted entry → ABORT. |
| JNL-03 | Line check: exactly one of debit/credit non-zero, ≥ 0. | valid line. | both sides, both zero, negative → constraint error. |
| JNL-04 | Idempotent posting by source key. | repeat returns same id. | row count unchanged. |
| JNL-05 | Reversal entries for refunds. | reversal mirrors lines with swapped sides; net zero. | reversing twice → no second entry. |
| JNL-06 | Cash summary definition. | matches §11 on fixture (dues+ticket+merch, expense paid, one unsettled). | clearing and obligations are not counted as cash. |
| JNL-07 | Drill-down totals reconcile. | total = Σ accounts = Σ entries = Σ source docs. | missing source link fails integrity page. |
| JNL-08 | Integrity check. | `check-integrity` exit 0 on clean data. | corrupt data (test creates via direct SQL on a copy) → exit 1 with named failure. |
| JNL-09 | Reports exclude DRAFT entries and other terms. | term filter correct. | entries in another term not summed. |

## G. Expenses and receipts

| ID | Requirement | + | − |
|----|-------------|---|---|
| EXP-01 | Submit expense with category, amount, optional links to event/task/fundraiser. | stored SUBMITTED; links queryable. | amount ≤ 0, unknown link, invalid category → 422. |
| EXP-02 | Private receipts. | owner and `receipts.view_all` can download. | other users and anonymous → 404/401; direct guessing of stored_name via `/static` → 404. |
| EXP-03 | Upload limits. | png/jpeg/pdf ≤ 5 MB OK. | `.exe`, oversize, wrong magic bytes (png extension, html body) → `UPLOAD_REJECTED`; filename path traversal sanitized. |
| EXP-04 | Approve/reject by `expenses.approve`; approver ≠ submitter. | treasurer approves → journal Dr5xxx/Cr2100. | self-approval → `SELF_APPROVAL`; member → 403; rejected expense has no journal. |
| EXP-05 | Payment (reimbursement) by `expenses.pay`. | APPROVED→PAID, Dr2100/Cr1000. | SUBMITTED → 409; double pay → idempotent, one entry. |
| EXP-06 | Receipt required to pay. | pay with ≥1 receipt works. | pay with none → 422. |
| EXP-07 | Expense drill-down. | finance page shows expense under category with link to receipt and fundraiser. | unlinked expenses still counted in category totals. |

## H. Comms, tasks

| ID | Requirement | + | − |
|----|-------------|---|---|
| COM-01 | Public announcements list/detail. | published visible, ordered newest first. | DRAFT hidden from public and non-publishers. |
| COM-02 | Publish enqueues one mail per subscriber. | N subscribers → N outbox rows. | publish twice → still N; unsubscribed excluded. |
| COM-03 | Subscribe/unsubscribe. | subscribe, token-link unsubscribe, status UNSUBSCRIBED. | invalid token → 404; duplicate subscribe is idempotent; invalid email → 422. |
| COM-04 | Local mail capture/history. | `process-mail` creates `mail_capture`; `/dev/mail` lists. | no SMTP calls (socket blocked in test); failing row retried max 3 then FAILED; viewer permission required. |
| COM-05 | Announcement history keeps authorship/time. | published_at, author shown. | editing a published announcement is blocked (or creates a visible revision; default: blocked). |
| TSK-01 | Fundraiser tasks with owner, deadline, status. | create, assign, move statuses. | invalid status/transition → 422; assign non-existent user → 422. |
| TSK-02 | On-track view. | board shows counts per status and overdue count. | tasks of other fundraisers not mixed. |
| TSK-03 | Task owner can update own task status. | owner PATCH ok. | other member → 403. |
| TSK-04 | Expense links to fundraiser/task. | fundraiser page shows spend vs goal. | link to task of another fundraiser → 422. |

## I. Close and handover

| ID | Requirement | + | − |
|----|-------------|---|---|
| CLS-01 | Checklist blocks close with unresolved items. | clean fixture closes. | each of 7 checks failing individually → `CLOSE_BLOCKED` naming the check; no snapshot, term still OPEN. |
| CLS-02 | Snapshot immutable with hash. | `content_sha256` recomputes from `totals_json`. | UPDATE/DELETE on snapshot → ABORT. |
| CLS-03 | Close is atomic. | after close: snapshot + CLOSED + new OPEN term all present. | inject failure after snapshot insert → rollback; none present. |
| CLS-04 | Closed term is read-only. | reads work. | inserting journal entries/payments/expenses for closed term → rejected `TERM_CLOSED`. |
| CLS-05 | Purchases after close go to new term. | new ticket sale posts to new term. | none posted into closed term. |
| CLS-06 | Corrections after close via adjusting entries. | adjusting entry in open term with `adjusts_term_id`; shown under "adjustments". | snapshot unchanged; adjustment without memo or without `close.run` rejected. |
| CLS-07 | Handover. | roles moved, `officer_handover` row, old sessions revoked. | before close → rejected; sole-admin removal rejected; old officer's cookie → 401; old officer's permissions gone immediately. |
| CLS-08 | Memberships expire at term transition. | previous ACTIVE ones EXPIRED. | new term's PENDING/ACTIVE not touched. |

## J. Cross-cutting

| ID | Requirement | + | − |
|----|-------------|---|---|
| CMD-01 | `expire-holds`, `send-reminders`, `process-mail`, `settle`, `migrate`, `seed`, `check-integrity` exist and are idempotent. | each runs twice with same final state (snapshot of table counts). | unknown flag → non-zero exit. |
| MIG-01 | Migrations apply cleanly in order on empty DB; `schema_migrations` recorded. | apply all; rerun is no-op. | tampered/missing file order → error. |
| SEC-01 | SQL uses parameters only. | static test greps for f-string/concat SQL in app code. | any hit fails (allow-list for table names). |
| SEC-02 | Output escaping. | announcement with `<script>` renders escaped. | no `|safe` on user content (static check). |
| SEC-03 | Cookie flags. | HttpOnly, SameSite=Lax. | no tokens in URLs or logs. |
| UXA-01 | Accessibility baseline. | each page has `<title>`, one `<h1>`, labelled inputs, focus order, 4.5:1 contrast on tokens, keyboard-operable check-in. | axe-core (if available offline) reports 0 serious/critical; failures recorded verbatim in evidence. |
| UXA-02 | Mobile check-in/purchase usable at 360 px. | screenshots without horizontal scroll. | recorded in evidence. |
| E2E-01 | **First slice:** join → dues → ACTIVE → discounted ticket → check-in → journal/report. | one test walks the whole flow via HTTP; asserts member price, ticket USED, 2 payments' journal entries balanced, cash summary and event report numbers. | same flow with failed dues payment: no discount, no journal entry. |
| E2E-02 | Full semester flow including merch, expense, settle, close, handover. | passes on a seeded fixture. | late-payment obligation blocks close until resolved. |
| EVD-01 | Evidence records actual outcomes. | `evidence/RUN-<date>.md` contains raw command output, git hash, counts. | a "not run" item is explicitly listed; CI check rejects an evidence file containing a score without an adjacent raw-output block. |
