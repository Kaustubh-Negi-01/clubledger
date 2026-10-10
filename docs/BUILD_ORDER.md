# ClubLedger Build Order

Four people, 24 hours. Estimates are planning guesses, not commitments. Hours are from kickoff (H0).

## 1. Repository layout and file ownership

Each file has exactly one owner. Edits to another owner's file go through that owner (or a small PR they approve). Shared files are listed explicitly.

```
pyproject.toml, pytest.ini, .gitignore, README.md        A
clubledger/
  main.py                    A   app factory, router registration (only place routers are mounted)
  config.py                  A
  cli.py                     A   command dispatcher; B/C add modules registering subcommands in their own files
  core/{db,auth,clock,pricing,errors,csrf,idgen}.py   A
  payments/{service,webhook,simulator,routes}.py      A
  migrations/0001_core.sql, 0002_payments.sql         A
  migrations/0003_membership.sql, 0004_events.sql, 0005_store.sql   B
  migrations/0006_journal.sql                         C  (written FIRST, see §2)
  migrations/0007_expenses.sql ... 0010_close.sql     C
  membership/{service,routes,cli}.py                  B
  events/{service,routes,cli}.py                      B
  store/{service,routes,cli}.py                       B
  web/templates/base.html, web/static/*, components   B   (base UI owns layout + HTMX + CSRF header)
  web/templates/<area>/*.html                         area owner (membership/events/store = B; rest = C)
  journal/{service,routes?}.py                        C
  reports/{service,routes}.py                         C
  expenses/{service,routes,receipts}.py               C
  comms/{service,routes,cli}.py                       C
  tasks/{service,routes}.py                           C
  close/{service,routes}.py, handover/{service,routes}.py   C
tests/                       D   (all; conftest.py, req_coverage.py, factories; D does not edit app code)
evidence/                    D
docs/                        shared; CONTRACT/REQUIREMENTS/BUILD_ORDER changes need A + D sign-off
scripts/{sim_webhook.py,demo_seed.py}                A
```

**Migration ownership and numbering are reserved above** so there are no merge collisions: filenames are fixed, and a migration is only edited by its owner. Cross-owner FKs only reference tables from lower-numbered migrations. `0006_journal.sql` has no FKs to B tables (uses `source_type/source_id`).
Dependency order for migration application: 0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010. (`payments.ref_table/ref_id` is polymorphic, so 0002 does not depend on 0003–0005.)

**Interfaces between owners (frozen at H2; change only by agreement):** the signatures in CONTRACT.md §13. Until a real implementation exists, A provides stubs in `clubledger/_stubs.py` that raise `NotImplementedError`, so everyone can import and type against them on day one.

## 2. Dependency graph

```
A: core/db+migrate+auth ──┬── payments ──────────────────────────────┐
                          │                                          │
C: journal (0006 + service, tiny, FIRST) ────────────────────────────┤  payments calls journal.post_*
                          │                                          │
B: base UI ───────────────┼── membership ── events ── store          │
                          │       │           │         │            │
                          │       └─ fulfillers registered with payments.FULFILLERS
                          │
C (after journal): reports → expenses → comms → tasks → close → handover
D: test harness+factories (H0-H3) → tests per area as each lands → e2e → a11y → evidence
```

Hard blockers:
1. `core/db.py` + `migrate` CLI (A) blocks everyone's DB work → **done by H1**.
2. `journal.post_entry` (C) blocks payments' end-to-end and all reports → **done by H2** (small: ~80 lines + triggers).
3. `core/auth.py` + `base.html` (A + B) block any authenticated page → **H3**.
4. `payments.handle_event` + `FULFILLERS` registry (A) blocks fulfillment tests → **H4**.

## 3. Timeline

| Hours | A (core/auth/db/payments/integration) | B (UI/membership/events/store) | C (journal → rest) | D (tests/a11y/evidence) |
|---|---|---|---|---|
| H0–1 | repo scaffold, `config`, `core/db.py`, `migrate`, `0001`, `0002` | `base.html`, nav, design tokens, HTMX + CSRF header snippet | `0006_journal.sql` + triggers, accounts seed | `pytest.ini`, `conftest.py` (temp DB, clock, client), `req_coverage.py` |
| H1–2 | `auth` (register/login/logout/session/CSRF/perm dep), `seed` roles | `0003`, `0004` migrations; membership plans seed | `journal.service` (`post_entry`, `reverse_entry`, `post_payment_received`) + unit tests | factories (user, role, session, event, plan); journal tests JNL-01..05 written |
| H2–3 | `pricing.py`, `payments.service` skeleton, simulator routes | `/join`, `/events` list/detail pages (read-only) | `post_settlement`, `post_refund`, `cash_summary`, reports skeleton | AUTH-* and PAY-02..05 tests |
| H3–5 | `handle_event` (validation order), `FULFILLERS`, `settle`, `expire` hooks | `fulfill_dues`, `member_code/qr`, `/members/card`, `/verify` | `reports` pages, drill-down | MEM-*, PAY-* tests |
| H5–7 | refund, mismatch/late-success/obligation handling | `create_hold`, `fulfill_ticket_hold`, ticket page, check-in, event report | `0007` expenses+receipts, submit/approve/pay + journal | EVT-*, E2E-01 (first slice) |
| **H7** | **First-slice milestone: E2E-01 green or stop and fix** | | | |
| H7–10 | `cli` commands wiring, `check-integrity`, security sweep (CSRF route sweep, SQL grep) | store: `0005`, reserve/fulfill/expire/pickup/refund, UI | `0008` comms + `process-mail` + mail viewer; `0009` tasks board | STO-*, EXP-*, COM-* tests |
| H10–14 | integration bugs, admin payments page, concurrency tests support | admin pages (events, store, members), mobile polish | `0010` close + snapshot + handover | CLS-*, concurrency tests (EVT-03, STO-08) |
| H14–18 | demo seed, README, run-through | UI polish, empty/error states | integrity page, adjusting entries | a11y pass (UXA-01/02), E2E-02 |
| H18–22 | bug fixing from D's evidence | bug fixing | bug fixing | full run, `evidence/RUN-*.md` with raw output |
| H22–24 | freeze, tag, final `check-integrity` | demo rehearsal | demo data | final evidence; list failures honestly |

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

**Minimum scope for the slice:** one plan, one event, `settle` optional (clearing shown separately), no expiry, no refunds, no emails. **Done when** `tests/e2e/test_first_slice.py::E2E-01` passes: member price applied, ticket USED, all journal entries balanced, event report = 1 sold / 1 attended, proceeds = member price, cash summary clearing = dues + ticket.

## 5. Integration protocol

- Branches: `codex/contracts` (this), then `a/*`, `b/*`, `c/*`, `d/*`; merge to `main` through PRs with one reviewer from another owner. `main` must always pass `pytest -q`.
- Contract drift: if an implementation needs a signature change, edit CONTRACT.md in the same PR and tag A + D.
- Every PR runs: `pytest -q`, `python -m tests.req_coverage`, `python -m clubledger.cli check-integrity` on seeded demo.
- Cut lines if time is short (in order dropped): handover → adjusting entries → task board polish → refunds for merch → announcement mail revision rules. Never drop: PAY-02..05, PAY-08, PAY-10, JNL-01..02, EVT-03/05, AUTH-05/07, E2E-01.

## 6. Defaults chosen (to avoid scope debates)

Single `INR` currency; one open term at a time (academic year); ticket hold TTL 10 min, merch reservation TTL 15 min, payment expiry 30 min; settlement T+1 with no fees; one plan "Member" at ₹ (seeded) with 20% ticket and 10% merch discounts; max 4 tickets per order; receipts ≤ 5 MB; scrypt via stdlib; dev mail only (no SMTP); no timezone handling beyond UTC with IST display formatting in templates.
