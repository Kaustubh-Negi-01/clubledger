"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { DEMO_COOKIE, demoAllowed, isDemo, supabaseServer } from "@/lib/db";
import { run, type ActionState } from "@/lib/action";
import { AppError } from "@/lib/db/errors";
import { DEMO_PERSONAS } from "@/lib/db/demo";
import { safeNext } from "@/lib/safe-next";

function allowedDomain(email: string) {
  const list = (process.env.ALLOWED_EMAIL_DOMAINS ?? "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
  if (!list.length) return true;
  return list.includes(email.split("@")[1]?.toLowerCase() ?? "");
}

/** Demo only: sign in as one of the seeded people. */
export async function demoSignIn(userId: string, next: string) {
  if (!isDemo || !demoAllowed) throw new Error("Demo sign-in is disabled.");
  if (!DEMO_PERSONAS.some((p) => p.id === userId)) throw new Error("Unknown demo user");
  (await cookies()).set(DEMO_COOKIE, userId, { httpOnly: true, sameSite: "lax", path: "/", maxAge: 60 * 60 * 8 });
  redirect(safeNext(next));
}

export async function passwordAuth(_: ActionState, fd: FormData): Promise<ActionState> {
  return run(async () => {
    if (isDemo) throw new AppError("VALIDATION", "Email sign-in needs Supabase. Pick a demo person below instead.");
    const email = String(fd.get("email") ?? "").trim().toLowerCase();
    const password = String(fd.get("password") ?? "");
    const mode = String(fd.get("mode") ?? "signin");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) throw new AppError("VALIDATION", "Enter a valid email address");
    if (password.length < 8) throw new AppError("VALIDATION", "Use a password of at least 8 characters");
    if (!allowedDomain(email)) throw new AppError("FORBIDDEN", "That email domain is not allowed to join this club");
    const sb = await supabaseServer();
    if (mode === "signup") {
      const name = String(fd.get("name") ?? "").trim();
      const { data, error } = await sb.auth.signUp({
        email,
        password,
        options: { data: { full_name: name }, emailRedirectTo: `${process.env.NEXT_PUBLIC_SITE_URL}/auth/callback` },
      });
      if (error) throw new AppError("VALIDATION", error.message);
      if (!data.session) return "Check your inbox to confirm your email, then sign in.";
    } else {
      const { error } = await sb.auth.signInWithPassword({ email, password });
      if (error) throw new AppError("VALIDATION", "Wrong email or password");
    }
    redirect(safeNext(fd.get("next")));
  });
}

export async function magicLink(_: ActionState, fd: FormData): Promise<ActionState> {
  return run(async () => {
    if (isDemo) throw new AppError("VALIDATION", "Email links need Supabase. Pick a demo person below instead.");
    const email = String(fd.get("email") ?? "").trim().toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) throw new AppError("VALIDATION", "Enter a valid email address");
    if (!allowedDomain(email)) throw new AppError("FORBIDDEN", "That email domain is not allowed to join this club");
    const sb = await supabaseServer();
    const next = encodeURIComponent(safeNext(fd.get("next")));
    const { error } = await sb.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${process.env.NEXT_PUBLIC_SITE_URL}/auth/callback?next=${next}` },
    });
    if (error) throw new AppError("VALIDATION", error.message);
    return "Magic link sent. Check your inbox.";
  });
}

export async function signOut() {
  if (isDemo) (await cookies()).delete(DEMO_COOKIE);
  else await (await supabaseServer()).auth.signOut();
  redirect("/");
}
