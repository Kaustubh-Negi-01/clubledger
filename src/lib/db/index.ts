import "server-only";
import { cookies } from "next/headers";
import { createServerClient } from "@supabase/ssr";
import { demoRpc } from "./demo";
import { Json } from "./json";
import { AppError, toAppError } from "./errors";

export { Json, AppError } from "./index-exports";

export const isDemo = !process.env.NEXT_PUBLIC_SUPABASE_URL || !process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
export const DEMO_COOKIE = "cl_demo_user";
/**
 * The demo database is for previews. A production deployment that lost its Supabase variables must not
 * silently turn into an open demo club, so it needs an explicit DEMO_MODE=1 there.
 */
export const demoAllowed = process.env.VERCEL_ENV !== "production" || process.env.DEMO_MODE === "1";

/**
 * The single door to the database. Production: Supabase (the signed-in user's JWT reaches Postgres, so auth.uid() works).
 * Preview: the in-process demo database. Either way the call lands on the same api_* SQL function.
 */
export async function rpc<T = unknown>(fn: string, args: Record<string, unknown> = {}): Promise<T> {
  try {
    if (isDemo) {
      if (!demoAllowed) throw new AppError("INTERNAL", "This deployment is not connected to a database yet. Set the Supabase environment variables.");
      const jar = await cookies();
      return await demoRpc<T>(jar.get(DEMO_COOKIE)?.value ?? null, fn, args);
    }
    const supabase = await supabaseServer();
    const clean = Object.fromEntries(Object.entries(args).map(([k, v]) => [k, v instanceof Json ? v.value : v]));
    const { data, error } = await supabase.rpc(fn, clean);
    if (error) throw new Error(error.message);
    return data as T;
  } catch (e) {
    throw toAppError(e);
  }
}

export async function supabaseServer() {
  const jar = await cookies();
  return createServerClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!, {
    cookies: {
      getAll: () => jar.getAll(),
      setAll: (list) => {
        try {
          list.forEach(({ name, value, options }) => jar.set(name, value, options));
        } catch {
          /* called from a Server Component: the proxy refreshes the session instead */
        }
      },
    },
  });
}
