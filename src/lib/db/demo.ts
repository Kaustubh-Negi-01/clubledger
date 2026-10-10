import "server-only";
import { PGlite } from "@electric-sql/pglite";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { Json } from "./json";

/**
 * No-credentials preview database: the real migrations and the demo seed running in an in-process Postgres.
 * Identical SQL to production, so behaviour matches. State lives in memory and resets when the server restarts.
 */
type Holder = { db?: Promise<PGlite>; queue: Promise<unknown> };
const g = globalThis as unknown as { __clubledgerDemo?: Holder };
const holder: Holder = (g.__clubledgerDemo ??= { queue: Promise.resolve() });

async function boot(): Promise<PGlite> {
  const root = join(process.cwd(), "supabase");
  const db = new PGlite();
  await db.exec("set time zone 'UTC'");
  await db.exec(readFileSync(join(root, "dev", "pglite_prelude.sql"), "utf8"));
  for (const f of readdirSync(join(root, "migrations")).filter((x) => x.endsWith(".sql")).sort()) {
    await db.exec(readFileSync(join(root, "migrations", f), "utf8"));
  }
  await db.exec(readFileSync(join(root, "dev", "demo_seed.sql"), "utf8"));
  await db.exec("select set_config('request.jwt.claim.sub', '', false)");
  return db;
}

export const DEMO_PERSONAS = [
  { id: "00000000-0000-4000-8000-000000000004", name: "Maya Fernandes", role: "Member", blurb: "Active member with tickets and a hoodie order" },
  { id: "00000000-0000-4000-8000-000000000005", name: "Dev Malhotra", role: "Signed up, not a member", blurb: "Pays public prices until they join" },
  { id: "00000000-0000-4000-8000-000000000003", name: "Ishaan Verma", role: "Door and store volunteer", blurb: "Checks tickets in and hands over orders" },
  { id: "00000000-0000-4000-8000-000000000002", name: "Rohan Kapoor", role: "Treasurer", blurb: "Approves expenses, settles payouts, closes the term" },
  { id: "00000000-0000-4000-8000-000000000001", name: "Priya Nair", role: "President (admin)", blurb: "Runs events, announcements and the team" },
] as const;

export function demoDb(): Promise<PGlite> {
  return (holder.db ??= boot());
}

function pgValue(v: unknown): unknown {
  if (v === undefined) return null;
  if (Array.isArray(v)) return "{" + v.map((x) => '"' + String(x).replace(/(["\\])/g, "\\$1") + '"').join(",") + "}";
  if (v !== null && typeof v === "object") return JSON.stringify(v);
  return v;
}

/** Runs one api_* call as `userId` (or anonymous). Serialised: PGlite has a single connection. */
export function demoRpc<T>(userId: string | null, fn: string, args: Record<string, unknown>): Promise<T> {
  const run = async () => {
    const db = await demoDb();
    await db.query("select set_config('request.jwt.claim.sub', $1, false)", [userId ?? ""]);
    const keys = Object.keys(args);
    const named = keys.map((k, i) => `${k} => $${i + 1}`).join(", ");
    const vals = keys.map((k) => {
      const v = args[k];
      return v instanceof Json ? JSON.stringify(v.value) : pgValue(v);
    });
    const res = await db.query<{ r: T }>(`select public.${fn}(${named}) as r`, vals);
    return res.rows[0]?.r as T;
  };
  const next = holder.queue.then(run, run);
  holder.queue = next.catch(() => undefined);
  return next;
}
