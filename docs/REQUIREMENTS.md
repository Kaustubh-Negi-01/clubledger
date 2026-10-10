# ClubLedger Requirements and Test Map

Every requirement has an ID. Every ID maps to at least one positive (`+`) and one negative (`-`) planned test. Nothing here has been run; these are plans, not results.

## Test conventions

- **Scope count.** This file defines **108** requirement IDs (`req_coverage` prints the live count; if it differs from 108 this sentence is stale). Cut-line deferrals (BUILD_ORDER.md §5) are the only way an ID leaves the accepted scope, and each deferral must be recorded in `tests/req_status.json` with a reason.
- **Markers.** `pytest.ini` (owned by D): `markers = req(id, kind): requirement ID from docs/REQUIREMENTS.md; kind is "pos" or "neg"`, `addopts = --strict-markers`. Each test carries e.g. `@pytest.mark.req("MEM-03", "pos")`. A test may carry several.
- **Status file.** `tests/req_status.json` (D) maps every ID to `planned | implemented | deferred`. Owners flip an ID to `implemented` in the same PR that lands its tests and code.
- **Checker.** `python -m tests.req_coverage --mode progress|final` (D):
  - `progress` (used by early CI on every PR): fails on (a) a marker naming an unknown ID, (b) an `implemented` ID without at least one passing `pos` and one passing `neg` test, (c) a test that references a `planned` ID without being marked xfail/skip. It prints `implemented N / total M`, **never** treats unimplemented IDs as failures, and exits 0 while the project is incomplete.
  - `final` (release gate, run before the final evidence): fails if any ID that is not `deferred` is not `implemented`, if any `deferred` ID lacks a recorded reason, or if any non-deferred ID lacks a passing `pos` and `neg` test. The accepted scope is therefore the complete ID list minus recorded deferrals.
- **Ownership.** D owns `pytest.ini`, `tests/conftest.py`, `tests/factories.py`, `tests/req_coverage.py`, `tests/req_status.json`, `tests/e2e/`, `tests/a11y/`, `tests/contract/` (static checks). Implementers write unit tests under `tests/unit/<area>/` using D's fixtures (`db`, `app_client`, `clock`, `make_user`, `make_event`, `login_as`); they do not edit D's files (changes go to D by PR). A's `pyproject.toml` contains no pytest settings.
- Test IDs are `tests/<area>/test_<file>.py::<name>`. Areas: `auth`, `payments`, `membership`, `events`, `store`, `journal`, `expenses`, `comms`, `tasks`, `close`, `e2e`, `a11y`, `contract`.
- D writes tests from this file independently of implementers (HTTP routes, CLI, and DB reads for assertions). Owners' unit tests are welcome, but D's suite is the evidence of record.
- Time is controlled with `core.clock.set_now()` (test env only). Each test uses a fresh temp SQLite file and applies migrations.
- Evidence (`evidence/`): `pytest -q` output saved verbatim with date, git hash, and counts; `req_coverage` output; axe/manual accessibility notes; screenshot paths. If something was not run, the file says "not run". No scores are invented.

## A. Auth, sessions, CSRF, permissions

| ID | Requirement | + Positive test | − Negative test |
|----|-------------|-----------------|-----------------|
| AUTH-01 | Registration creates a user with no membership benefits. | register → `/me` shows "not a member"; ticket price shown = public. | duplicate email (case-insensitive) → 422. |
| AUTH-02 | Passwords stored as scrypt hash; login verifies. | login ok sets HttpOnly cookie. | wrong password → 401, no session row. |
| AUTH-03 | Sessions expire by absolute (8 h, `absolute_expires_at`) and sliding idle (2 h, `idle_expires_at`) limits; refresh at most every 60 s and never past the absolute limit. | request at +1h59m works, `last_seen_at`/`idle_expires_at` advance; two requests 10 s apart write at most once. | idle +2h01m → 401; activity every 30 min still → 401 at +8h01m (`absolute_expires_at` unchanged); revoked → 401. |
| AUTH-04 | Logout invalidates the session server-side. | logout → `revoked_at` set. | replaying the old cookie → 401. |
| AUTH-05 | Role revocation takes effect on the next request. | grant `door`, `/checkin` 200. | revoke role (cookie unchanged) → same cookie now 403. |
| AUTH-06 | Deactivating a user revokes their sessions. | deactivate → all session rows revoked. | old cookie → 401. |
| AUTH-07 | Browser mutations require CSRF. | POST with valid token succeeds. | missing/foreign-session token → 403 `CSRF_FAILED`, no mutation (checked for every POST route via route table sweep). |
| AUTH-08 | `/webhooks/payments` is the only CSRF exemption. | signed webhook without CSRF works. | route sweep: any other mutating route without CSRF returns 403; webhook with bad signature → 400. |
| AUTH-09 | Ownership: users access only their own payments/tickets/orders/receipts. | owner GET 200. | other user GET → 404 for `/tickets/{id}`, `/pay/{id}`, `/me/orders`, `/receipts/{id}`. |
| AUTH-10 | Permissions are explicit; `comms.mail_viewer` and `receipts.view_all` not implied. | `comms` role sees `/dev/mail`. | `events` and `door` roles → 403 on `/dev/mail`, others' receipts. |
| AUTH-11 | Purchases require login. | logged-in non-member can hold a ticket at public price. | anonymous POST hold/reserve/join → 401/redirect to login. |
| AUTH-12 | Rate limits (clock-driven buckets): login 5/min per (IP,email), register 10/h, subscribe 10/h, webhook 60/min, verify lookup 60/min, check-in 120/min. | after advancing the injected clock 60 s a throttled login is accepted again. | 6th login in a minute from one IP+email → 429 with `Retry-After`; flooding the webhook with bad signatures → 429 and still zero DB writes. |
| AUTH-13 | Developer routes are gated: `/dev/mail*` exist only when `CLUBLEDGER_ENV` is `dev`/`test` and need `comms.mail_viewer`; server refuses non-loopback bind in `dev`. | env=test + comms user → 200. | env=prod → 404 even for an admin; env=dev with host `0.0.0.0` → startup error; user without permission → 403. |

## B. Payments

| ID | Requirement | + | − |
|----|-------------|---|---|
| PAY-01 | Money is integer paise; client cannot set amount. | hold response amount == server price. | POST with extra `amount`/`price` field is ignored (price unchanged). |
| PAY-02 | Webhook signature/timestamp/schema validated before **any** database write. | valid signature applies (row inserted, state changed). | bad signature, stale timestamp (6 min), bad JSON, oversize body → 400; DB row counts and file content identical before/after, including `audit_log` and `payment_events` (rejections appear only in the log file). |
| PAY-03 | After a valid signature, event identity/currency/amount/type are validated; mismatches never modify the payment and never discard verified money. | exact match applies. Mismatched amount/currency/user/unknown payment → `payment_events.outcome=UNAPPLIED_RECEIPT` with reason; an INR amount is booked Dr1100/Cr2000. | the target payment row, fulfillment and the ticket/membership/order are unchanged; non-INR or 0-amount event creates no journal entry but still blocks close until resolved; `payment.failed` with mismatch → `NO_EFFECT`. |
| PAY-04 | Failed/pending events grant nothing. | `payment.failed` → FAILED. | no ticket/membership/order created; no journal entry; capacity still held until expiry. |
| PAY-05 | Duplicate `event_id` is a no-op that preserves the first outcome. | second delivery of the same body returns 200 with the *original* outcome. | tickets, journal and `payment_events` rows unchanged after 3 replays; stored `outcome`/`reason` unchanged; direct UPDATE of `outcome` aborts (trigger). |
| PAY-06 | Simulator signs server-side. | browser outcome post succeeds. | response body and templates never contain the secret or a `v1=` signature; ownership check blocks other users. |
| PAY-07 | A prior failure does not discard later verified money. | fail then valid success → status SUCCEEDED, fulfillment UNFULFILLED, journal Dr1100/Cr2000, reason `LATE_AFTER_FAILED`. | no ticket/membership/order is granted automatically; a second success for the now-SUCCEEDED payment → `UNAPPLIED_RECEIPT` (`DUPLICATE_RECEIPT`). |
| PAY-08 | Late success after expiry → UNFULFILLED obligation (never discarded). | expire hold, payment EXPIRED, then valid success: SUCCEEDED + UNFULFILLED, journal Dr1100/Cr2000, reason `LATE_AFTER_EXPIRED`; listed in `/admin/payments?problem=1`. | no ticket issued; 4100 unchanged; 2000 balance == amount; capacity not consumed. |
| PAY-09 | Every UNFULFILLED payment and UNAPPLIED_RECEIPT has a resolution path. | REFUND: reversal entries, `RESOLVED_REFUNDED` / `resolution=REFUNDED`, 2000 → 0. FULFILL (term OPEN, seat free): EXPIRED hold → CONSUMED, N tickets with seat_index 1..N, Dr2000/Cr4100. DISMISS with note on a receipt event reverses its entries. | FULFILL when the event is now full → `SOLD_OUT`, obligation remains; FULFILL when the payment's term is CLOSED → rejected, REFUND still works; DISMISS without note → 422; non-staff → 403. |
| PAY-10 | One outer transaction; fulfillment and journal atomic. | success leaves ticket + 1 journal entry. | inject journal failure → rollback: no ticket, payment still PENDING, hold still HELD; retry with same event succeeds. |
| PAY-11 | No nested transactions. | static test greps services for `BEGIN`/`COMMIT`/`ROLLBACK` (only `core/db.py` allowed). | adding a nested `BEGIN` in a fixture raises; services receive an in-transaction conn (`conn.in_transaction` True). |
| PAY-12 | Full refunds only; eligibility depends on fulfillment. | FULFILLED refund restores everything per type; an UNFULFILLED payment refunds with no ticket/order/membership present. | no amount parameter accepted (422); refund of REFUNDED/FAILED/EXPIRED payment → 409. |
| PAY-13 | Refund rejected after use/pickup. | unused ticket refund ok. | ticket USED → `REFUND_BLOCKED`; merch PICKED_UP → `REFUND_BLOCKED`; nothing changes. |
| PAY-14 | Dues refund revokes entitlement. | membership REVOKED; next ticket price = public. | check-in/verify shows not a member. |
| PAY-15 | Settlement/cash treatment and refunds as exact reversals. | before `settle`: cash 0, clearing = X; after: cash X, clearing 0. Refund before settle posts one `received_reversal` (Dr income, Cr 1100). Refund after settle also posts `settled_reversal` (Dr1100/Cr1000); clearing ends 0, cash drops by X. | second `settle` run posts nothing; each reversal mirrors the original lines exactly (swapped sides); a payment cannot be reversed twice (`ux_entries_reversal`). |
| PAY-16 | Idempotent journal effects. | each of received/settled/refunded exists once per payment. | replaying handler functions directly does not duplicate (unique key). |
| PAY-17 | Late callbacks after term close: a payment created in a closed term, then EXPIRED/FAILED, receives a valid success after close. | payment SUCCEEDED+UNFULFILLED; entry posts to the OPEN term with a prior-term memo; closed term's journal totals and snapshot unchanged; REFUND resolves it in the OPEN term. | FULFILL is rejected because `payment.term_id` is not OPEN; no fulfillment is attempted automatically. |
| PAY-18 | Unauthenticated requests cannot reserve trusted event IDs; reuse is detected. | after a rejected (bad-signature) request carrying `event_id=E`, a *valid* event with `event_id=E` still applies normally. | same `event_id` with a different body (valid signature) → 409 `EVENT_ID_REUSED`, no mutation. |

## C. Membership

| ID | Requirement | + | − |
|----|-------------|---|---|
| MEM-01 | Join creates PENDING membership + payment at plan price. | amount == plan dues. | PENDING gives no discount and `verify` shows not active. |
| MEM-02 | Dues success activates membership; sets `starts_at`/`expires_at` from the academic-year bounds, plus `member_code` and `qr_token`. | fields set. | dues failure → stays PENDING. |
| MEM-03 | Benefits: discounted ticket and merch price for ACTIVE only. | member price on ticket + merch. | PENDING/EXPIRED/REVOKED/non-member pay public price. |
| MEM-04 | No duplicate live membership per user per membership year; next-year renewal allowed from `expires_at − 30 days`. | renewal for the next year is accepted while the current financial term is still OPEN; next year's `starts_at == current.expires_at`. | second join for the same year → `ALREADY_MEMBER`; renewal earlier than 30 days → 422. |
| MEM-05 | Annual expiry from the Asia/Kolkata academic year (1 Aug 00:00 IST, stored UTC). | at the `expires_at` boundary membership is inactive; `send-reminders` flips status to EXPIRED; stored values end in `T18:30:00Z`. | one second before the boundary still active; consecutive years leave no gap (year N `expires_at` == year N+1 `starts_at`). |
| MEM-06 | Renewal reminders at 30 d, 7 d, and expiry, once each, via `dedupe_key`. | clock at T−30d: 1 mail queued (`process-mail` → captured). | rerun same day → no new row (UNIQUE `dedupe_key`); member who already renewed → `SUPPRESSED` (`MEMBERSHIP_RENEWED`) with no capture; inactive user → suppressed; non-members never mailed. |
| MEM-07 | Staff verification by code or QR. | `verifier` role sees name + ACTIVE. | no role → 403; unknown code → "not found"; expired → "EXPIRED"; page doesn't expose email/payment info. |
| MEM-08 | Price tier frozen at hold time. | membership bought after hold does not reprice that hold. | membership revoked after hold does not reprice either. |
| MEM-09 | Closing a financial term (early or on time) never changes memberships. | close a term 4 months before the academic year ends; an ACTIVE member is still ACTIVE and still gets the member price afterwards. | no `memberships` row changes status or dates as a result of close (table diff before/after). |

## D. Events and tickets

| ID | Requirement | + | − |
|----|-------------|---|---|
| EVT-01 | Events list shows member and public prices and seats left. | values match DB. | DRAFT events hidden from public. |
| EVT-02 | Member vs public ticket price chosen server-side. | member pays member price. | non-member pays public; forged `price_tier` field ignored. |
| EVT-03 | Capacity reservation counts HELD + ISSUED + USED. | capacity 2: hold 2 ok. | third hold → `SOLD_OUT`; concurrent holds (two threads, one seat) → exactly one succeeds. |
| EVT-04 | Hold TTL and expiry release capacity once. | `expire-holds` after TTL frees seats. | running it twice does not free twice (capacity never exceeds `capacity`); expired hold can't be paid into tickets (→ PAY-08). |
| EVT-05 | Hold consumption releases held capacity exactly once and creates one ticket per seat. | qty 3 → 3 tickets with `seat_index` 1,2,3 and distinct codes; held=0 and available = capacity − 3 after fulfillment. | a second fulfillment attempt raises (guarded `UPDATE` rowcount 0) and creates no more tickets; direct INSERT of a duplicate `(hold_id, seat_index)` fails; rollback mid-way leaves hold HELD and zero tickets. |
| EVT-06 | Unique opaque ticket codes; quantity limits. | codes are random base32, unique across tickets. | qty 0 or 11 → 422; qty > `max_per_order` → 422; codes are not sequential or guessable. |
| EVT-07 | Check-in by QR text or manual code. | first scan → USED, `used_at`, `used_by`. | second scan → `ALREADY_USED` (shows first time); unknown code → not found; other event's ticket → rejected; REFUNDED ticket → rejected. |
| EVT-08 | Check-in is staff-only. | `door` role 200. | member/anonymous → 403/401. |
| EVT-09 | Event report is computed from ticket prices and reconciled to the journal without joining payments to tickets. | fixture with mixed tiers, a 3-seat order and one full refund: `sold`, `attended`, `no_shows`, `gross`, `refunded`, `net_proceeds` correct (each ticket counted once). | for every ticket payment, net 4100 journal credit (separate aggregate) == Σ price of its ISSUED/USED tickets; unfulfilled payments excluded from both; a 3-seat order of price P reports 3P, never 9P. |
| EVT-10 | Free ticket (unit price 0): login required, capacity consumed, no payment or journal. | hold is created already CONSUMED and tickets have `payment_id NULL`. | anonymous → 401; capacity exceeded → `SOLD_OUT`; no refund path exists (no payment). |
| EVT-11 | Event cancel: paid tickets are refunded via the normal path (REFUNDED); free tickets become VOID. | each payment with all-ISSUED tickets → REFUNDED payment and REFUNDED tickets; free tickets → VOID. | a payment with any USED ticket is not refunded and is flagged; VOID never appears on a ticket that has a payment (CHECK). |
| EVT-12 | Old event after close: events created in a closed term stay purchasable while ON_SALE. | after close, a new sale for an earlier-term event gets the new term's `term_id` and posts income to the OPEN term; event report shows a per-term split. | no journal entry is inserted into the CLOSED term (trigger); a CLOSED/CANCELLED event cannot be bought. |

## E. Store

| ID | Requirement | + | − |
|----|-------------|---|---|
| STO-01 | Variants expose physical, reserved and available stock; shoppers see *available*. | listing shows `physical_qty − reserved_qty` per size. | available 0 → size disabled; inactive product hidden; `reserved_qty > physical_qty` impossible (CHECK). |
| STO-02 | Cart reservation is atomic. | a cart of 3 lines increases `reserved_qty` on all 3 variants. | one line short → `INSUFFICIENT_STOCK` and **no** variant's `reserved_qty` changed. |
| STO-03 | Quantity validation. | qty 1–10 accepted. | 0, negative, 11, non-int, duplicate variant lines → 422. |
| STO-04 | Server-authoritative merch price with member discount. | member discounted (floor math). | forged price ignored; total == Σ(unit×qty). |
| STO-05 | Payment success → PAID. | order PAID, one journal entry to 4200; `reserved_qty` unchanged until pickup. | failure/expiry decrements `reserved_qty` exactly once. |
| STO-06 | Reservation expiry releases reserved stock once. | after TTL `reserved_qty` is restored. | rerun does not release twice; late success → UNFULFILLED (PAY-08/PAY-09); manual FULFILL re-reserves or fails with `INSUFFICIENT_STOCK`. |
| STO-07 | Pickup by staff reduces physical and reserved stock. | PAID → PICKED_UP: both `physical_qty` and `reserved_qty` fall by qty. | unpaid/RESERVED → 409; non-staff → 403; second pickup → 409. |
| STO-08 | Oversell race. | two concurrent carts for the last unit: exactly one wins. | `reserved_qty` never exceeds `physical_qty`. |
| STO-09 | Refund before pickup restores reserved stock. | `reserved_qty` falls by qty, order REFUNDED. | after pickup → `REFUND_BLOCKED`; physical stock unchanged by a refund. |

## F. Journal and reports

| ID | Requirement | + | − |
|----|-------------|---|---|
| JNL-01 | Posted entries balance; direct inserts of POSTED entries are rejected. | `post_entry` balanced posts via DRAFT → lines → POSTED. | unbalanced → error; direct `INSERT` of an entry with `status='POSTED'` (valid or invalid) aborts; flipping an unbalanced or one-line draft to POSTED aborts. |
| JNL-02 | Posted entries are immutable, including line movement. | reads OK. | INSERT a line into a POSTED entry, UPDATE/DELETE its lines, UPDATE a line's `entry_id` into a POSTED entry, move a line out of a POSTED entry, UPDATE/DELETE the posted entry → all ABORT. |
| JNL-03 | Line check: exactly one of debit/credit non-zero, ≥ 0. | valid line. | both sides, both zero, negative → constraint error. |
| JNL-04 | Idempotent posting by source key. | repeat returns same id. | row count unchanged. |
| JNL-05 | Reversal entries are exact mirrors and happen once. | reversal lines equal the original with sides swapped; net zero. | reversing twice → no second entry (`ux_entries_reversal`); a `*_reversal` without `reverses_entry_id` is rejected. |
| JNL-06 | Cash summary = cumulative balance as of a cutoff, never a term-filtered sum. | fixture over two terms: cash after rollover equals Σ of all POSTED 1000 lines before the cutoff. | term-filtered movement is not used for cash; clearing and obligations are not counted as cash; an `as_of` in the past excludes later entries. |
| JNL-07 | Drill-down totals reconcile. | total = Σ accounts = Σ entries = Σ source docs. | missing source link fails integrity page. |
| JNL-08 | Integrity check. | `check-integrity` exit 0 on clean data. | corrupt data (test creates via direct SQL on a copy) → exit 1 with named failure. |
| JNL-09 | Reports exclude DRAFT entries and other terms. | term filter correct. | entries in another term not summed. |
| JNL-10 | Balances vs movements: opening(N+1) == closing(N) for every balance account; movements are per term. | after close + rollover, the cash summary still shows prior cash; the movement report for the new term shows only new activity. | income/expense movement of term N is unaffected by term N+1 activity; snapshot closing balances equal live `balance_as_of(ends_at)`. |
| JNL-11 | No closed-term insertion path. | a new entry (including an adjustment) with the OPEN `term_id` and `adjusts_term_id` = a CLOSED term posts. | inserting an entry with a CLOSED `term_id` aborts (`TERM_CLOSED`) even with `adjusts_term_id` or `source_type='adjustment'`; `adjusts_term_id` pointing to the OPEN term is rejected. |

## G. Expenses and receipts

| ID | Requirement | + | − |
|----|-------------|---|---|
| EXP-01 | Submit expense with category, amount, optional links to event/fundraiser/task. | stored SUBMITTED; links queryable; a task link requires that task's own fundraiser. | amount ≤ 0, unknown link, category outside 5000–5099 → 422; task from another fundraiser → composite FK error → 422. |
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
| COM-02 | Publish enqueues one mail per subscriber via `dedupe_key`. | N subscribers → N outbox rows with `announcement:{id}:{email}` keys. | publish twice → still N; unsubscribed addresses excluded at enqueue. |
| COM-03 | Subscribe/unsubscribe. | subscribe, token-link unsubscribe, status UNSUBSCRIBED. | invalid token → 404; duplicate subscribe is idempotent; invalid email → 422; unsubscribe also applies to already-queued mail (COM-04). |
| COM-04 | Local mail capture is exactly-once and re-checks eligibility before sending. | `process-mail` writes one `mail_capture` per SENT row; `/dev/mail` lists captured and suppressed rows. | subscriber unsubscribes after enqueue → row `SUPPRESSED` (`UNSUBSCRIBED`), no capture; running `process-mail` twice → still one capture (UNIQUE `outbox_id`); no SMTP/socket use; failing row retried max 3 then FAILED; viewer permission required. |
| COM-05 | Published announcements keep authorship/time and are not editable. | `published_at` and author shown. | edit of a PUBLISHED announcement → rejected. |
| TSK-01 | Fundraiser tasks with owner, deadline, status. | create, assign, move statuses. | invalid status/transition → 422; assign non-existent user → 422. |
| TSK-02 | On-track view. | board shows counts per status and overdue count. | tasks of other fundraisers not mixed. |
| TSK-03 | Task owner can update own task status. | owner PATCH ok. | other member → 403. |
| TSK-04 | Expense links to fundraiser/task. | fundraiser page shows spend vs goal. | link to a task of another fundraiser → 422. |

## I. Close and handover

| ID | Requirement | + | − |
|----|-------------|---|---|
| CLS-01 | Checklist blocks close with unresolved items. | clean fixture closes. | each of the 8 checks failing individually (including UNFULFILLED payment, unresolved UNAPPLIED_RECEIPT, non-zero cumulative 2000/2100/1100) → `CLOSE_BLOCKED` naming it; no snapshot, term still OPEN, nothing written. |
| CLS-02 | Snapshot is immutable, hashed, and holds opening/movement/closing per account. | `content_sha256` recomputes from `totals_json`; closing balances match `balance_as_of(ends_at)`. | UPDATE/DELETE on snapshot → ABORT. |
| CLS-03 | Close is atomic. | after close: snapshot + CLOSED term + new OPEN term (`starts_at == previous ends_at`) all present. | inject failure after snapshot insert → rollback; none present, term still OPEN, no second OPEN term possible (`ux_terms_one_open`). |
| CLS-04 | Closed-term journal data is read-only. | reads work. | new payments/expenses/holds always carry the OPEN `term_id`; a journal insert with a CLOSED `term_id` → `TERM_CLOSED` (trigger). |
| CLS-05 | Purchases after close go to new term. | new ticket sale posts to new term. | none posted into closed term. |
| CLS-06 | Corrections after close are adjusting entries in the OPEN term. | adjustment (OPEN `term_id`, `adjusts_term_id` = closed term, memo) posts and appears under 'Adjustments to prior terms'. | snapshot unchanged; missing memo or missing `close.run` rejected; no way to post into the closed term (JNL-11). |
| CLS-07 | Handover. | roles moved, `officer_handover` row, old sessions revoked. | before close → rejected; sole-admin removal rejected; old officer's cookie → 401; old officer's permissions gone immediately. |
| CLS-08 | Term transition is contiguous and independent of memberships. | next term `starts_at` equals the closed term's `ends_at` exactly; early close at any time works. | no gap or overlap across three consecutive closes; membership rows untouched (MEM-09). |
| CLS-09 | Late callbacks after close are handled explicitly (see PAY-17). | the late success posts in the OPEN term and is listed as UNFULFILLED until resolved. | it never lands in the closed term's entries and never alters the already-taken snapshot. |

## J. Cross-cutting

| ID | Requirement | + | − |
|----|-------------|---|---|
| CMD-01 | `expire-holds`, `send-reminders`, `process-mail`, `settle`, `migrate`, `seed`, `check-integrity` exist and are idempotent; `reset-db` and `--as-of` are dev/test only. | each runs twice with the same final state (table-count snapshot). | unknown flag → non-zero exit; `--as-of` or `reset-db` with `CLUBLEDGER_ENV=prod` → refused. |
| MIG-01 | Migrations apply strictly by number, contiguously, with checksums; every FK points to a lower-numbered table. | apply all on an empty DB; rerun is a no-op; a static test confirms the dependency order in CONTRACT.md §1; every table is STRICT. | missing number (e.g. 0005 deleted) → refuses to run; edited applied file → checksum error naming `reset-db`. |
| SEC-01 | SQL uses parameters only. | static test greps for f-string/concat SQL in app code. | any hit fails (allow-list for table names). |
| SEC-02 | Output escaping. | announcement with `<script>` renders escaped. | no `|safe` on user content (static check). |
| SEC-03 | Cookie flags. | HttpOnly, SameSite=Lax. | no tokens in URLs or logs. |
| SEC-04 | Clock discipline. | `set_now` works under `CLUBLEDGER_ENV=test`. | `set_now` raises otherwise; static test finds no `datetime.now`/`time.time` outside `core/clock.py`. |
| SEC-05 | Browser idempotency keys are scoped to actor, action and request. | same user+action+key+params replayed → original result, no second hold/order/membership. | same key with different params → 422 `IDEMPOTENCY_CONFLICT`; another user or action reusing the key cannot read or consume it. |
| SEC-06 | Handler wiring is explicit and cycle-free. | `wiring.build_services()` returns handlers for DUES/TICKET/MERCH; importing each package in isolation succeeds. | static test: `payments` imports none of membership/events/store; no module mutates a registry at import time. |
| UXA-01 | Accessibility baseline of behavior and markup (visual design is deferred). | each page has `<title>`, one `<h1>`, labelled inputs, keyboard-operable check-in, 4.5:1 contrast on any defined color tokens. | axe-core (if available offline) reports 0 serious/critical; failures are recorded verbatim in evidence. |
| UXA-02 | Mobile check-in/purchase usable at 360 px. | screenshots without horizontal scroll. | recorded in evidence. |
| E2E-01 | **First slice:** join → dues → ACTIVE → discounted ticket → check-in → journal/report. | one test walks the whole flow via HTTP; asserts member price, ticket USED, 2 payments' journal entries balanced, cash summary and event report numbers. | same flow with failed dues payment: no discount, no journal entry. |
| E2E-02 | Full semester flow including merch, expense, settle, close, handover. | passes on a seeded fixture. | late-payment obligation blocks close until resolved. |
| EVD-01 | Evidence records actual outcomes. | `evidence/RUN-<date>.md` contains raw command output, git hash, counts. | a "not run" item is explicitly listed; CI check rejects an evidence file containing a score without an adjacent raw-output block. |
