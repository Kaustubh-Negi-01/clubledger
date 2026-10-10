import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

/**
 * Daily housekeeping (Vercel Cron): expires holds, reservations and payments, queues renewal reminders.
 * Idempotent. Requires CRON_SECRET and the service role key; without them it refuses.
 */
export async function GET(request: Request) {
  const secret = process.env.CRON_SECRET;
  if (!secret || request.headers.get("authorization") !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) return NextResponse.json({ error: "supabase not configured" }, { status: 503 });
  const sb = createClient(url, key, { auth: { persistSession: false } });
  const { data, error } = await sb.rpc("maintenance_run");
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true, result: data });
}
