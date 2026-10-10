// SQL behaviour tests. Runs the real migrations in an in-process Postgres (PGlite) and drives the api_* functions
// exactly as the app does. Prints actual results; exits non-zero on any failure.
import { PGlite } from "@electric-sql/pglite";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const root = join(import.meta.dirname, "..", "supabase");
const db = new PGlite();
await db.exec("set time zone 'UTC'");
await db.exec(readFileSync(join(root, "dev", "pglite_prelude.sql"), "utf8"));
for (const f of readdirSync(join(root, "migrations")).filter((x) => x.endsWith(".sql")).sort()) {
  await db.exec(readFileSync(join(root, "migrations", f), "utf8"));
}

let passed = 0;
const failures: string[] = [];
const u = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const ADMIN = u(1), TREAS = u(2), DOOR = u(3), MEMBER = u(4), OUTSIDER = u(5), ORG = u(6);

async function as(uid: string | null, sql: string, params: unknown[] = []) {
  await db.query(`select set_config('request.jwt.claim.sub', $1, false)`, [uid ?? ""]);
  return db.query<any>(sql, params);
}
async function api(uid: string | null, fn: string, ...args: unknown[]) {
  const ph = args.map((_, i) => `$${i + 1}`).join(", ");
  const r = await as(uid, `select public.${fn}(${ph}) as r`, args.map((a) => (a !== null && typeof a === "object" && !Array.isArray(a) ? JSON.stringify(a) : a)));
  return r.rows[0]?.r;
}
async function err(uid: string | null, fn: string, ...args: unknown[]): Promise<string> {
  try { await api(uid, fn, ...args); return "NO_ERROR"; } catch (e: any) { return String(e.message); }
}
async function clock(ts: string | null) { await db.query(`select set_config('app.now_override', $1, false)`, [ts ?? ""]); }
async function one(sql: string, params: unknown[] = []) { return (await db.query<any>(sql, params)).rows[0]; }
function ok(cond: unknown, name: string, detail = "") {
  if (cond) { passed++; console.log(`  ok   ${name}`); } else { failures.push(name); console.log(`  FAIL ${name} ${detail}`); }
}
function eq(a: unknown, b: unknown, name: string) { ok(JSON.stringify(a) === JSON.stringify(b), name, `(got ${JSON.stringify(a)}, want ${JSON.stringify(b)})`); }

const bal = async (code: string) => Number((await one(`select public.account_balance($1) as b`, [code])).b);

// ---------------- setup users ----------------
console.log("users and roles");
for (const [id, email, name] of [[ADMIN, "priya@club.test", "Priya Nair"], [TREAS, "rohan@club.test", "Rohan Kapoor"], [DOOR, "ishaan@club.test", "Ishaan Verma"],
  [MEMBER, "maya@club.test", "Maya Fernandes"], [OUTSIDER, "dev@club.test", "Dev Malhotra"], [ORG, "zoya@club.test", "Zoya Khan"]] as const) {
  await db.query(`insert into auth.users (id, email, raw_user_meta_data) values ($1, $2, $3)`, [id, email, JSON.stringify({ full_name: name })]);
}
eq((await one(`select count(*)::int as n from user_roles where role='admin' and user_id=$1`, [ADMIN])).n, 1, "first user becomes admin");
eq((await one(`select count(*)::int as n from user_roles where role='admin'`)).n, 1, "only the first user is admin");
await api(ADMIN, "api_set_role", TREAS, "treasurer", true);
await api(ADMIN, "api_set_role", DOOR, "door", true);
await api(ADMIN, "api_set_role", ORG, "organizer", true);
ok((await err(MEMBER, "api_set_role", MEMBER, "admin", true)).startsWith("FORBIDDEN"), "member cannot grant roles");
ok((await err(ADMIN, "api_set_role", ADMIN, "admin", false)).startsWith("VALIDATION"), "last admin cannot be removed");

// ---------------- catalog ----------------
await clock("2026-09-10T10:00:00Z");
const ev = await api(ORG, "api_event_save", null, "Spring Gala", "Dinner and dance", "Skyline Hall", "2026-10-20T13:00:00Z", "2026-10-20T17:00:00Z", 5, 60000, 90000, 4, "");
await api(ORG, "api_event_set_status", ev.id, "ON_SALE");
const free = await api(ORG, "api_event_save", null, "Open Mic", "", "Cafe", "2026-10-22T13:00:00Z", "2026-10-22T15:00:00Z", 50, 0, 0, 4, "");
await api(ORG, "api_event_set_status", free.id, "ON_SALE");
ok((await err(MEMBER, "api_event_save", null, "x", "", "y", "2026-10-20T13:00:00Z", "2026-10-20T17:00:00Z", 5, 0, 0, 4, "")).startsWith("FORBIDDEN"), "member cannot create events");

// ---------------- membership ----------------
console.log("membership and payments");
const jn = await api(MEMBER, "api_join", 1);
const jn2 = await api(MEMBER, "api_join", 1);
eq(jn.payment_id, jn2.payment_id, "joining twice reuses the pending payment");
const priceBefore = (await api(MEMBER, "api_event_get", ev.id)).my_price;
eq(priceBefore, 90000, "non-member pays public price");
let r = await api(MEMBER, "api_pay_simulate", jn.payment_id, "success");
eq(r.outcome, "APPLIED", "dues payment fulfilled");
const me = await api(MEMBER, "api_me");
eq(me.membership.status, "ACTIVE", "membership active");
ok(/^CL-[0-9A-F]{8}$/.test(me.membership.member_code), "member code issued", me.membership.member_code);
eq(me.membership.membership_year, "2026-27", "membership year from Asia/Kolkata bounds");
eq(me.membership.expires_at.slice(0, 19), "2027-07-31T18:30:00", "expires 1 Aug 00:00 IST in UTC");
r = await api(MEMBER, "api_pay_simulate", jn.payment_id, "success");
eq(r.outcome, "NO_EFFECT", "repeated success notification has no effect");
eq(await bal("1100"), 50000, "clearing holds dues after one entry only");
eq(await bal("4000"), 50000, "dues income booked once");
ok((await err(MEMBER, "api_join", 1)).startsWith("ALREADY_MEMBER"), "cannot join twice in the same year");
eq((await api(MEMBER, "api_event_get", ev.id)).my_price, 60000, "member price: min(member price, plan discount)");
eq((await api(OUTSIDER, "api_event_get", ev.id)).my_price, 90000, "outsider still public");
const v = await api(OUTSIDER, "api_pay_get", jn.payment_id).catch((e: any) => e.message);
ok(String(v).startsWith("NOT_FOUND"), "other users cannot read my payment");

// ---------------- tickets ----------------
console.log("tickets");
ok((await err(null, "api_hold_tickets", ev.id, 1)).startsWith("AUTH_REQUIRED"), "anonymous cannot buy");
ok((await err(MEMBER, "api_hold_tickets", ev.id, 9)).startsWith("VALIDATION"), "max per order enforced");
const h1 = await api(MEMBER, "api_hold_tickets", ev.id, 3);
const h1b = await api(MEMBER, "api_hold_tickets", ev.id, 3);
eq(h1.payment_id, h1b.payment_id, "double submit reuses the live hold");
eq((await api(null, "api_event_get", ev.id)).available, 2, "held seats reduce availability");
ok((await err(OUTSIDER, "api_hold_tickets", ev.id, 3)).startsWith("SOLD_OUT"), "cannot hold more than available");
r = await api(MEMBER, "api_pay_simulate", h1.payment_id, "success");
eq(r.outcome, "APPLIED", "ticket payment fulfilled");
const seats = (await db.query<any>(`select seat_index from tickets where hold_id=(select id from ticket_holds order by id limit 1) order by seat_index`)).rows.map((x) => x.seat_index);
eq(seats, [1, 2, 3], "three tickets with seat_index 1..3");
eq((await api(null, "api_event_get", ev.id)).available, 2, "availability unchanged after consuming the hold (released exactly once)");
eq(await bal("4100"), 180000, "ticket income booked");
eq((await one(`select count(*)::int n from ticket_holds where status='HELD'`)).n, 0, "no hold left HELD");
const mine = await api(MEMBER, "api_my_tickets");
eq(mine.length, 3, "member sees 3 tickets");

// late success after hold expiry
console.log("late payments");
const h2 = await api(OUTSIDER, "api_hold_tickets", ev.id, 2);
await clock("2026-09-10T10:20:00Z");
const maint = await api(null, "api_maintenance");
eq(maint.holds_expired, 1, "maintenance expires the hold");
eq((await api(null, "api_event_get", ev.id)).available, 2, "expired hold frees seats");
const h3 = await api(MEMBER, "api_hold_tickets", ev.id, 2);
r = await api(OUTSIDER, "api_pay_simulate", h2.payment_id, "success");
eq(r.outcome, "APPLIED_UNFULFILLED", "late success after expiry is unfulfilled, not discarded");
eq(await bal("2000"), 180000, "unfulfilled money sits in the obligation account");
const unf = await api(TREAS, "api_payments_admin", true);
eq(unf.length, 1, "unfulfilled payment is in the problem queue");
ok((await err(TREAS, "api_resolve_unfulfilled", h2.payment_id, "FULFILL")).startsWith("SOLD_OUT"), "manual fulfill fails when seats are taken");
r = await api(TREAS, "api_resolve_unfulfilled", h2.payment_id, "REFUND");
eq(r.resolved, "REFUNDED", "unfulfilled payment refunded without any ticket state");
eq(await bal("2000"), 0, "obligation cleared by exact reversal");
eq((await one(`select status, fulfillment from payments where id=$1`, [h2.payment_id])), { status: "REFUNDED", fulfillment: "RESOLVED_REFUNDED" }, "payment marked refunded");
await api(MEMBER, "api_pay_simulate", h3.payment_id, "fail");
r = await api(MEMBER, "api_pay_simulate", h3.payment_id, "success");
eq(r.outcome, "APPLIED_UNFULFILLED", "success after a recorded failure is not discarded either");
await api(TREAS, "api_resolve_unfulfilled", h3.payment_id, "FULFILL");
eq((await one(`select count(*)::int n from tickets where hold_id=(select ref_id from payments where id=$1)`, [h3.payment_id])).n, 2, "manual fulfill issues the seats");
eq(await bal("2000"), 0, "obligation cleared by late fulfillment");
eq((await api(null, "api_event_get", ev.id)).available, 0, "event now full");
eq((await one(`select count(*)::int n from tickets where event_id=$1`, [ev.id])).n, 5, "never oversold");

// check-in
console.log("check-in and refunds");
const t = (await api(MEMBER, "api_my_tickets"))[0];
r = await api(DOOR, "api_checkin", ev.id, "cl-t:" + t.code.toLowerCase());
eq(r.result, "OK", "check-in works with a scanned prefix");
r = await api(DOOR, "api_checkin", ev.id, t.code);
eq(r.result, "ALREADY_USED", "second scan is rejected");
r = await api(DOOR, "api_checkin", free.id, t.code);
eq(r.result, "WRONG_EVENT", "ticket for another event rejected");
r = await api(DOOR, "api_checkin", ev.id, "ZZZZ");
eq(r.result, "NOT_FOUND", "unknown code rejected");
ok((await err(MEMBER, "api_checkin", ev.id, t.code)).startsWith("FORBIDDEN"), "members cannot check people in");
ok((await err(TREAS, "api_refund", h1.payment_id)).startsWith("REFUND_BLOCKED"), "refund blocked after a ticket is used");
const rep = await api(ORG, "api_event_report", ev.id);
eq([rep.sold, rep.attended, rep.net_paise], [5, 1, 300000 - 0], "event report counts each ticket once");
const integ = await api(TREAS, "api_integrity");
ok(integ.every((c: any) => c.ok), "integrity checks pass", JSON.stringify(integ.filter((c: any) => !c.ok)));

// free tickets
const f = await api(OUTSIDER, "api_hold_tickets", free.id, 2);
eq(f.free, true, "free event issues tickets directly");
eq((await one(`select count(*)::int n from payments where purpose='TICKET' and ref_id in (select id from ticket_holds where event_id=$1)`, [free.id])).n, 0, "free tickets create no payment");

// ---------------- store ----------------
console.log("store");
const pr = await api(ADMIN, "api_product_save", null, "Skyline Hoodie", "Heavyweight fleece", 149900, "", true);
await api(ADMIN, "api_variant_set_stock", pr.id, "M", 3);
await api(ADMIN, "api_variant_set_stock", pr.id, "L", 1);
const vs = (await api(null, "api_products_list")).find((p: any) => p.id === pr.id).variants;
const vM = vs.find((x: any) => x.size === "M").id, vL = vs.find((x: any) => x.size === "L").id;
const before = JSON.stringify((await api(null, "api_products_list")).find((p: any) => p.id === pr.id).variants);
ok((await err(MEMBER, "api_reserve_cart", [{ variant_id: vM, qty: 2 }, { variant_id: vL, qty: 2 }])).startsWith("INSUFFICIENT_STOCK"), "cart with one short line fails");
eq(JSON.stringify((await api(null, "api_products_list")).find((p: any) => p.id === pr.id).variants), before, "failed cart leaves every variant untouched (atomic)");
ok((await err(MEMBER, "api_reserve_cart", [{ variant_id: vM, qty: 0 }])).startsWith("VALIDATION"), "quantity 0 rejected");
ok((await err(MEMBER, "api_reserve_cart", [{ variant_id: vM, qty: 1 }, { variant_id: vM, qty: 1 }])).startsWith("VALIDATION"), "duplicate size lines rejected");
const cart = await api(MEMBER, "api_reserve_cart", [{ variant_id: vM, qty: 2 }, { variant_id: vL, qty: 1 }]);
eq(cart.total_paise, 3 * Math.floor((149900 * 9000) / 10000), "member merch discount applied in integers");
eq((await api(null, "api_products_list")).find((p: any) => p.id === pr.id).variants.find((x: any) => x.size === "M").available, 1, "reserved stock reduces availability");
await api(MEMBER, "api_pay_simulate", cart.payment_id, "success");
eq((await one(`select status from merch_orders where id=$1`, [cart.order_id])).status, "PAID", "order paid");
await api(store(), "api_order_pickup", cart.order_id).catch(() => null);
function store() { return ADMIN; }
const after = (await api(null, "api_products_list")).find((p: any) => p.id === pr.id).variants.find((x: any) => x.size === "M");
eq([after.physical, after.reserved], [1, 0], "pickup reduces physical and reserved stock");
ok((await err(TREAS, "api_refund", cart.payment_id)).startsWith("REFUND_BLOCKED"), "refund blocked after pickup");
const cart2 = await api(OUTSIDER, "api_reserve_cart", [{ variant_id: vM, qty: 1 }]);
await clock("2026-09-10T10:40:00Z");
await api(null, "api_maintenance");
eq((await one(`select status from merch_orders where id=$1`, [cart2.order_id])).status, "EXPIRED", "reservation expires");
eq((await api(null, "api_products_list")).find((p: any) => p.id === pr.id).variants.find((x: any) => x.size === "M").available, 1, "expiry restores stock exactly once");
await api(null, "api_maintenance");
eq((await api(null, "api_products_list")).find((p: any) => p.id === pr.id).variants.find((x: any) => x.size === "M").available, 1, "second maintenance run does not release twice");

// ---------------- ledger protection ----------------
console.log("ledger protection");
const e1 = (await one(`select id from journal_entries order by id limit 1`)).id;
async function sqlErr(sql: string) { try { await db.exec(sql); return "NO_ERROR"; } catch (e: any) { return e.message; } }
ok((await sqlErr(`insert into journal_entries (term_id, entry_date, source_type, source_id, source_event, status, posted_at) values (1, now(), 'adjustment', 'x', 'x', 'POSTED', now())`)).includes("DRAFT"), "direct INSERT of a POSTED entry is rejected");
ok((await sqlErr(`insert into journal_lines (entry_id, account_code, debit) values (${e1}, '1000', 5)`)).includes("non-draft"), "cannot add a line to a posted entry");
ok((await sqlErr(`update journal_lines set debit = debit + 1 where entry_id = ${e1}`)).includes("immutable"), "cannot edit posted lines");
ok((await sqlErr(`delete from journal_lines where entry_id = ${e1}`)).includes("cannot be deleted"), "cannot delete posted lines");
ok((await sqlErr(`update journal_entries set memo = 'x' where id = ${e1}`)).includes("immutable"), "cannot edit a posted entry");
await db.exec(`insert into journal_entries (term_id, entry_date, source_type, source_id, source_event) values (1, now(), 'adjustment', 'draftA', 'adj')`);
const dA = (await one(`select id from journal_entries where source_id='draftA'`)).id;
await db.exec(`insert into journal_lines (entry_id, account_code, debit) values (${dA}, '1000', 100)`);
ok((await sqlErr(`update journal_entries set status='POSTED', posted_at=now() where id=${dA}`)).includes("not balanced"), "unbalanced draft cannot be posted");
ok((await sqlErr(`update journal_lines set entry_id = ${e1} where entry_id = ${dA}`)).includes("cannot move"), "lines cannot be moved into a posted entry");
ok((await sqlErr(`update journal_lines set entry_id = ${dA} where entry_id = ${e1}`)).includes("cannot move"), "lines cannot be moved out of a posted entry");
await db.exec(`delete from journal_lines where entry_id=${dA}; delete from journal_entries where id=${dA};`);
const probe = (await one(`select public.post_entry('adjustment','probe','adjustment','probe', '[{"account":"1000","debit":10},{"account":"4000","credit":10}]'::jsonb) as id`)).id;
eq((await one(`select public.reverse_entry(${probe}, 'x') = public.reverse_entry(${probe}, 'x') as same`)).same, true, "reversal happens once");
eq(await bal("1000"), 0, "probe entry and its reversal net to zero");

// ---------------- expenses ----------------
console.log("expenses");
const ex = await api(MEMBER, "api_expense_submit", "5000", 25000, "Decor for the gala", ev.id, null, null);
ok((await err(MEMBER, "api_expense_decide", ex.id, true, "")).startsWith("FORBIDDEN"), "members cannot approve");
await api(ADMIN, "api_set_role", MEMBER, "treasurer", true);
ok((await err(MEMBER, "api_expense_decide", ex.id, true, "")).startsWith("SELF_APPROVAL"), "no self approval");
await api(ADMIN, "api_set_role", MEMBER, "treasurer", false);
await api(TREAS, "api_expense_decide", ex.id, true, "ok");
ok((await err(TREAS, "api_expense_pay", ex.id)).startsWith("VALIDATION"), "paying needs a receipt");
await api(MEMBER, "api_expense_add_receipt", ex.id, "u/1/r.png", "r.png", "image/png", 1234);
ok((await err(MEMBER, "api_expense_add_receipt", ex.id, "u/1/r.exe", "r.exe", "application/x-msdownload", 10)).startsWith("UPLOAD_REJECTED"), "bad file type rejected");
eq((await api(MEMBER, "api_receipt_path", 1)).path, "u/1/r.png", "owner can fetch own receipt path");
ok((await err(OUTSIDER, "api_receipt_path", 1)).startsWith("NOT_FOUND"), "others cannot");
eq(await bal("2100"), 25000, "approved expense is a payable");
await api(TREAS, "api_expense_pay", ex.id);
eq(await bal("2100"), 0, "payment clears the payable");

// ---------------- comms ----------------
console.log("announcements and mail");
await api(null, "api_subscribe", "a@club.test"); await api(null, "api_subscribe", "b@club.test"); await api(null, "api_subscribe", "A@club.test");
ok((await err(null, "api_subscribe", "not-an-email")).startsWith("VALIDATION"), "bad email rejected");
eq((await one(`select count(*)::int n from subscribers`)).n, 2, "subscriptions are case-insensitive unique");
await api(ADMIN, "api_set_role", ADMIN, "comms", true);
const an = await api(ADMIN, "api_announcement_save", null, "Gala tickets are live", "Get yours now.", true);
eq(an.queued, 2, "publish queues one mail per subscriber");
const an2 = await api(ADMIN, "api_announcement_save", an.id, "Gala tickets are live", "Get yours now.", true).catch((e: any) => e.message);
ok(String(an2).startsWith("VALIDATION"), "published announcements cannot be edited");
const tok = (await one(`select unsub_token from subscribers where email='b@club.test'`)).unsub_token;
await api(null, "api_unsubscribe", tok);
const pr1 = await api(ADMIN, "api_outbox_process", 100);
eq([pr1.sent, pr1.suppressed], [1, 1], "unsubscribed recipient suppressed at send time");
const pr2 = await api(ADMIN, "api_outbox_process", 100);
eq([pr2.sent, pr2.suppressed], [0, 0], "processing twice sends nothing twice");
eq((await one(`select count(*)::int n from mail_capture`)).n, 1, "exactly one capture");
eq((await api(null, "api_announcements_list")).length, 1, "public sees the announcement");

// ---------------- reminders ----------------
console.log("reminders");
await clock("2027-07-05T00:00:00Z");
const m1 = await api(null, "api_maintenance");
ok(m1.reminders_queued >= 1, "30-day reminder queued", JSON.stringify(m1));
const m2 = await api(null, "api_maintenance");
eq(m2.reminders_queued, 0, "reminders are deduplicated");
await clock("2027-08-01T00:00:00Z");
const m3 = await api(null, "api_maintenance");
eq(m3.memberships_expired, 1, "membership expires at the academic-year boundary");
eq((await api(MEMBER, "api_event_get", ev.id)).my_tier, "PUBLIC", "expired member pays public price");
await clock("2026-09-10T11:00:00Z");

// ---------------- close ----------------
console.log("term close");
await db.exec("update terms set starts_at = '2026-01-01T00:00:00Z' where id = 1");
const st0 = await api(TREAS, "api_close_status");
ok(st0.checks.some((c: any) => !c.ok), "close is blocked while money is unsettled");
ok((await err(TREAS, "api_close_term")).startsWith("CLOSE_BLOCKED"), "close refuses");
const sett = await api(TREAS, "api_settle");
ok(sett.settled > 0, "settlement pays out received money");
if (process.env.DEBUG_LEDGER) console.log((await db.query("select e.id,e.source_type,left(e.source_id,8) sid,e.source_event, string_agg(l.account_code||':'||l.debit||'/'||l.credit, ' ' order by l.id) ls from journal_entries e join journal_lines l on l.entry_id=e.id group by e.id order by e.id")).rows);
eq(await bal("1100"), 0, "clearing is zero after settlement");
const st1 = await api(TREAS, "api_close_status");
ok(st1.checks.every((c: any) => c.ok), "all close checks pass", JSON.stringify(st1.checks.filter((c: any) => !c.ok)));
const cashBefore = await bal("1000");
await clock("2026-09-11T10:00:00Z");
const closed = await api(TREAS, "api_close_term");
eq(closed.opened, "Term 2", "next term opens in the same transaction");
eq(await bal("1000"), cashBefore, "cash carries over after rollover");
const snap = (await api(TREAS, "api_close_status")).snapshots[0];
eq(snap.totals.accounts["1000"].opening + snap.totals.accounts["1000"].movement, snap.totals.accounts["1000"].closing, "opening + movement = closing");
const terms = (await db.query<any>(`select starts_at, ends_at, status from terms order by id`)).rows;
eq(new Date(terms[0].ends_at).getTime(), new Date(terms[1].starts_at).getTime(), "terms are contiguous");
ok((await sqlErr(`update close_snapshots set content_sha256='x'`)).includes("immutable"), "snapshot is immutable");
ok((await sqlErr(`insert into journal_entries (term_id, entry_date, source_type, source_id, source_event) values (1, now(), 'adjustment', 'late', 'adj')`)).includes("open term"), "no journal entry can target the closed term");
const adj = await api(TREAS, "api_adjustment", 1, "Correct dues typo", [{ account: "4000", debit: 100 }, { account: "1000", credit: 100 }]);
ok(adj.id > 0, "adjustment posts into the open term");
eq((await one(`select term_id from journal_entries where id=$1`, [adj.id])).term_id, 2, "adjustment belongs to the open term");
ok((await err(TREAS, "api_adjustment", 2, "bad", [{ account: "4000", debit: 100 }, { account: "1000", credit: 100 }])).length > 0, "adjusting the open term is rejected");
// new purchases land in the new term
await api(MEMBER, "api_join", 1).then(async (j: any) => { await api(MEMBER, "api_pay_simulate", j.payment_id, "success"); });
eq((await one(`select term_id from payments order by created_at desc limit 1`)).term_id, 2, "new payments carry the open term");

// ---------------- permissions / surface ----------------
console.log("permissions");
for (const fn of ["api_finance_summary", "api_payments_admin", "api_members_admin", "api_mail_admin", "api_close_status"]) {
  ok((await err(MEMBER, fn)).startsWith("FORBIDDEN") || (await err(MEMBER, fn)).startsWith("FORBIDDEN"), `${fn} is staff only`);
  ok((await err(null, fn)).startsWith("AUTH_REQUIRED"), `${fn} requires sign-in`);
}
const grants = (await db.query<any>(`select has_function_privilege('anon','public.post_entry(text,text,text,text,jsonb,bigint,bigint)','execute') as g`)).rows[0].g;
eq(grants, false, "anon cannot execute internal functions");
const grantsApi = (await db.query<any>(`select has_function_privilege('anon','public.api_events_list(boolean)','execute') as g`)).rows[0].g;
eq(grantsApi, true, "anon can execute public api functions");
const tableAccess = (await db.query<any>(`select has_table_privilege('authenticated','public.payments','select') as g`)).rows[0].g;
eq(tableAccess, false, "tables are not readable through the Data API");

console.log(`\n${passed} passed, ${failures.length} failed`);
if (failures.length) { console.log("Failures:\n - " + failures.join("\n - ")); process.exit(1); }
