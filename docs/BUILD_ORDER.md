# ClubLedger Build Order

Four people, 24 hours. Hour figures are planning guesses, not commitments. Hours are from kickoff (H0). **UI/UX is deferred:** structural templates only until behavior is green; the lead's screenshot is a rough reference, not a requirement.

## 1. Repository layout and file ownership

Each file has exactly one owner. Edits to another owner's file go through that owner (or a small PR they approve).

```
pyproject.toml (dependencies, project metadata only), .gitignore, README.md   A
pytest.ini, tests/conftest.py, tests/factories.py, tests/req_coverage.py,
tests/req_status.json, tests/e2e/, tests/a11y/, tests/contract/, evidence/     D
tests/unit/<area>/                                                             area owner (uses D's fixtures)
clubledger/
  main.py                    A   app factory; calls wiring.build_services(); mounts routers
  wiring.py                  A   only module that imports all services together; builds Handlers/Services (CONTRACT §13.2)
  config.py                  A
  cli.py                     A   command dispatcher; B/C register subcommands from their own cli.py files
  core/{db,auth,clock,pricing,errors,csrf,idgen,types,ratelimit}.py   A   (types.py = shared types, CONTRACT §13.1)
  payments/{service,webhook,simulator,routes}.py      A
  migrations/0001_core.sql, 0002_payments.sql         A
  migrations/0003_membership.sql, 0004_events.sql, 0005_store.sql   B
  migrations/0006_journal.sql                         C  (written first, applied sixth; see §2)
  migrations/0007_tasks.sql, 0008_expenses.sql, 0009_comms.sql, 0010_close.sql   C
  membership/{service,routes,cli}.py                  B
  events/{service,routes,cli}.py                      B
  store/{service,routes,cli}.py                       B
  web/templates/base.html, web/static/*               B   structural base only (layout slots, HTMX, CSRF header); visual design deferred
  web/templates/<area>/*.html                         area owner (membership/events/store = B; payments/auth = A; the rest = C)
  journal/service.py                                  C
  reports/{service,routes}.py                         C
  tasks/{service,routes}.py                           C
  expenses/{service,routes,receipts}.py               C
  comms/{service,routes,cli}.py                       C
  close/{service,routes}.py, handover/{service,routes}.py   C
docs/                        shared; CONTRACT/REQUIREMENTS/BUILD_ORDER changes need A + D sign-off
scripts/{sim_webhook.py,demo_seed.py}                A
```

**Migration ownership and lifecycle.** Filenames and numbers are reserved above, but files exist only when genuine. There are no placeholder files. The migrator applies strictly by number over the contiguous available prefix, so development may proceed with `0001`–`0002` alone; it rejects internal gaps and changed applied migrations and never deletes a database (CONTRACT.md §1).
1. A lands `0001`, `0002` first. B lands `0003`, `0004`, `0005` as genuine migrations as they are written.
2. C authors `0006_journal.sql` early on `codex/treasury-comms` and tests the journal with a **test-only** fixture that applies the explicit subset `[0001, 0006]` (`0006` depends only on `terms`/`users`). Integration to `master` applies `0006` only after genuine `0003`–`0005` are on `master`; merging it earlier would create an internal gap. The subset fixture is not the production sequence.
3. Until a migration reaches `master`, its owner may edit it on their branch and rebuild local databases by hand (`reset-db --confirm <path>`, explicit, dev/test only). After it reaches `master` it is frozen; changes need a new file. Cross-owner FKs that would point at a later number are replaced by polymorphic `ref_table/ref_id` (payments) or reordered (tasks before expenses).

**Interfaces between owners (frozen at H2; change only by agreement and a docs update):** the types in CONTRACT.md §13.1 and signatures in §13.3. Until real implementations exist, A provides stubs in `clubledger/_stubs.py` raising `NotImplementedError` so everyone can import and type against them from H0.

**No import-time registration.** Handlers are passed explicitly: `wiring.build_services()` constructs the three `PurposeHandler`s and routes/CLI/tests pass them into `payments.service`. `payments` never imports membership/events/store; `core` ← `journal` ← `payments`; B modules import `core` and `payments.service.create_payment` only (CONTRACT §13.2).

## 2. Dependency graph

```
A: core/db+migrate+clock+types ─┬── auth ── payments (needs journal) ─────────┐
                                │                                            │
C: 0006 + journal.service (FIRST, small) ────────────────────────────────────┤  payments calls journal.post_*
                                │                                            │
B: structural base template ────┼── membership ── events ── store            │
                                │       └─ PurposeHandlers wired in wiring.py (A)
C (after journal): reports → tasks → expenses → comms → close → handover
D: pytest.ini/conftest/factories/req_coverage (H0–H2) → tests per area → e2e → a11y → evidence
```

Hard blockers:
1. `core/db.py` + `migrate` CLI (contiguous-prefix rules) + `0001`/`0002` (A) block everyone's DB work → **done by H1**.
2. `journal.post_entry` and the 0006 triggers (C) block payments end-to-end and every report → **done by H2**.
3. `core/auth.py` + structural `base.html` (A + B) block authenticated pages → **H3**.
4. `payments.handle_event` + `wiring.build_services` (A) block fulfillment tests → **H4**.
5. D's `conftest.py` fixtures block all owners' unit tests → **H1** (minimal fixtures), extended as areas land.

## 3. Timeline

| Hours | A (core/auth/db/payments/integration) | B (membership/events/store; structural UI) | C (journal → rest) | D (tests/a11y/evidence) |
|---|---|---|---|---|
| H0–1 | repo scaffold, `config`, `core/db.py`, `core/clock.py`, `core/types.py`, `migrate`, `0001`, `0002` | `base.html` slots + HTMX/CSRF header | `0006_journal.sql` (on `codex/treasury-comms`, tested with the [0001, 0006] subset fixture) + triggers, accounts seed | `pytest.ini`, `conftest.py` (temp DB, clock, client), `req_coverage.py`, `req_status.json`, early CI job (`--mode progress`) |
| H1–2 | `auth` (register/login/logout/session/CSRF/perm dep), `seed` roles, `ratelimit` | `0003`, `0004`; plans seed | `journal.service` (`post_entry`, reversals, `post_payment_received`) | factories; JNL-01..05 tests |
| H2–3 | `pricing.py`, `payments.service` skeleton, simulator routes | `/join`, `/events` read-only pages | `post_settlement`, `balance` (live/watermark/historical), `movement`, reports skeleton | AUTH-* and PAY-02..05 tests |
| H3–5 | `handle_event` (trusted/untrusted boundary), `wiring.py`, `settle`, `expire` hooks | `fulfill_dues`, `member_code/qr`, `/members/card`, `/verify` | reports pages, drill-down | MEM-*, PAY-* tests |
| H5–7 | refund, mismatch/late-success/obligation handling, `resolve_unfulfilled`/`resolve_receipt` | `create_hold`, `fulfill_ticket_hold`, ticket page, check-in, event report | `0007` tasks, `0008` expenses+receipts, submit/approve/pay + journal | EVT-*, E2E-01 (first slice) |
| **H7** | **First-slice milestone: E2E-01 green or stop and fix** | | | |
| H7–10 | `cli` wiring, `check-integrity`, security sweep (CSRF route sweep, SQL grep, clock grep) | store: `0005`, reserve/fulfill/expire/pickup/refund | `0009` comms + `process-mail` + mail viewer; tasks board | STO-*, EXP-*, COM-* tests |
| H10–14 | integration bugs, admin payments page | admin pages (events, store, members) | `0010` close + snapshot + handover | CLS-*, concurrency tests (EVT-03, STO-08) |
| H14–18 | demo seed, README, run-through | empty/error states, structural polish | integrity page, adjusting entries | a11y pass (UXA-01/02), E2E-02 |
| H18–22 | bug fixing from D's evidence | bug fixing | bug fixing | full run, `evidence/RUN-*.md` with raw output |
| H22–24 | freeze, final `check-integrity` | demo rehearsal | demo data | `req_coverage --mode final`, final evidence; failures listed honestly |

## 4. First vertical slice

**Flow:** join → dues → active membership → discounted ticket → check-in → journal/report.

| Step | Route / service | Owner | Needs |
|---|---|---|---|
| 1. Register, login | `/auth/*` | A | 0001, auth |
| 2. Join | `POST /join` → `membership.start_join` → `payments.create_payment` | B + A | 0002, 0003, pricing |
| 3. Pay dues | `/pay/{id}` → `POST …/outcome(success)` → `handle_event` → `fulfill_dues` → `journal.post_payment_received` (same conn) | A + B + C | journal H2 |
| 4. Active membership | `/members/card` shows code + QR; `/verify` confirms | B | |
| 5. Discounted ticket | `/events/{id}` shows member price → `POST …/hold` → pay → `fulfill_ticket_hold` | B + A | 0004 |
| 6. Check-in | `/checkin/{event}` with `door` role, scan code → `USED` | B | roles seed |
| 7. Journal/report | `/finance` cash summary and `/admin/events/{id}/report` | C + B | `cash_summary` |

**Minimum scope for the slice:** one plan, one event, `settle` optional (clearing shown separately), no expiry, no refunds, no emails. **Done when** `tests/e2e/test_first_slice.py` (marked E2E-01) passes: member price applied, ticket USED, all journal entries balanced, event report = 1 sold / 1 attended, proceeds = member price, cash summary clearing = dues + ticket.

## 5. Integration protocol

- **Branches.** `master` is the integration branch and must always pass early CI. The exact working branches are: `codex/contracts` (docs, current), `codex/core-payments` (A), `codex/member-events-store` (B), `codex/treasury-comms` (C), `codex/qa-evidence` (D). Sub-branches, if needed, extend the owner's branch name (e.g. `codex/core-payments-webhook`). Merge to `master` by PR with one reviewer from another owner; no one pushes to `master` directly.
- **Contract drift.** If an implementation needs a signature or schema change, edit CONTRACT.md in the same PR and tag A + D.
- **CI stages (do not pretend completeness).**
  - *Early CI (every PR, from H1):* `pytest -q`, `python -m tests.req_coverage --mode progress` (reports `implemented N / 108`; blocks on any failing test or static check, on unknown requirement IDs, and on an `implemented` ID without passing positive and negative tests; unimplemented requirements alone never block), static `tests/contract` checks (SQL parameterization, clock use, migration order/STRICT/FK dependency, no import-time registration).
  - *Final gate (H22+):* `python -m tests.req_coverage --mode final` — fails unless every ID is `implemented` or has a recorded deferral — plus `check-integrity` on a seeded demo. The final evidence discloses every deferral and the actual results; it is generated only from real runs.
- **Cut lines if time is short** (in order dropped, each recorded as `deferred` with a reason in `tests/req_status.json`): handover → adjusting entries UI (service stays) → task board polish → refunds for merch → announcement suppression edge cases. **Never dropped:** PAY-02..05, PAY-08, PAY-09, PAY-10, JNL-01, JNL-02, EVT-03, EVT-05, AUTH-05, AUTH-07, E2E-01.

## 6. Defaults chosen (to avoid scope debates)

Single `INR` currency; financial term is open-ended and ends at close (close can be early); membership year runs 1 Aug 00:00 IST to the next 1 Aug 00:00 IST (stored UTC, independent of terms); ticket hold TTL 10 min, merch reservation TTL 15 min, payment expiry 30 min; settlement T+1 with no fees; one plan "Member" with 20% ticket and 10% merch discounts (dues amount seeded); max 4 tickets per order; receipts ≤ 5 MB; scrypt via stdlib; dev mail capture only (no SMTP); display times in IST, stored in UTC; no tz database dependency (fixed +05:30).
