import "server-only";
import { rpc } from "./db";

let last = 0;

/**
 * Expiry of holds, reservations, payments and renewal reminders is idempotent SQL.
 * Run it opportunistically (at most every 20s per server) in addition to the daily Vercel cron.
 */
export async function maintain() {
  const now = Date.now();
  if (now - last < 20_000) return;
  last = now;
  try {
    await rpc("api_maintenance");
  } catch {
    /* never block a page render on housekeeping */
  }
}
