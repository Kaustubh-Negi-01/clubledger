import { NextResponse, type NextRequest } from "next/server";
import { supabaseServer, isDemo } from "@/lib/db";
import { safeNext } from "@/lib/safe-next";

function allowed(email: string | undefined) {
  const list = (process.env.ALLOWED_EMAIL_DOMAINS ?? "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
  if (!list.length) return true;
  return !!email && list.includes(email.split("@")[1]?.toLowerCase() ?? "");
}

export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = safeNext(searchParams.get("next"));
  if (isDemo || !code) return NextResponse.redirect(`${origin}/login?error=${encodeURIComponent("Sign-in link was invalid or expired")}`);

  const sb = await supabaseServer();
  const { error } = await sb.auth.exchangeCodeForSession(code);
  if (error) return NextResponse.redirect(`${origin}/login?error=${encodeURIComponent(error.message)}`);

  const { data } = await sb.auth.getUser();
  if (!allowed(data.user?.email)) {
    await sb.auth.signOut();
    return NextResponse.redirect(`${origin}/login?error=${encodeURIComponent("That email domain is not allowed to join this club")}`);
  }
  return NextResponse.redirect(`${origin}${next}`);
}
