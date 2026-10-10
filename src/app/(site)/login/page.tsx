import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { ArrowRight, Info } from "@phosphor-icons/react/dist/ssr";
import { isDemo } from "@/lib/db";
import { DEMO_PERSONAS } from "@/lib/db/demo";
import { getMe } from "@/lib/session";
import { demoSignIn } from "@/app/actions/auth";
import { AuthForms } from "./auth-forms";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string; error?: string }> }) {
  const { next = "/me", error } = await searchParams;
  const safeNext = next.startsWith("/") && !next.startsWith("//") ? next : "/me";
  if (await getMe()) redirect(safeNext);

  return (
    <div className="mx-auto grid min-h-[calc(100dvh-4rem)] max-w-7xl items-center gap-12 px-4 py-14 sm:px-6 lg:grid-cols-[1fr_minmax(0,28rem)]">
      <div className="hidden lg:block">
        <h1 className="display max-w-[14ch] text-6xl">Welcome back to the club.</h1>
        <p className="mt-6 max-w-md text-lg leading-relaxed text-muted">
          Tickets, your member card and your orders are all behind one sign-in. New here? Signing in creates your account.
        </p>
      </div>

      <div className="rounded-card border border-line bg-surface p-6 shadow-card sm:p-8">
        <h2 className="display text-3xl lg:hidden">Sign in</h2>
        <h2 className="hidden text-xl font-semibold tracking-tight lg:block">Sign in or create an account</h2>
        {error ? <p role="alert" className="mt-4 rounded-ctl bg-bad-soft px-3.5 py-2.5 text-sm text-bad">{decodeURIComponent(error)}</p> : null}

        {isDemo ? (
          <div className="mt-6">
            <div className="mb-5 flex gap-3 rounded-ctl bg-info-soft p-3.5 text-sm leading-relaxed text-info">
              <Info size={20} className="mt-0.5 shrink-0" weight="fill" />
              <p>
                Preview mode: no Supabase project is connected yet, so this runs on a built-in demo club. Pick a person to explore their view. Google sign-in appears here once Supabase is configured.
              </p>
            </div>
            <ul className="space-y-2">
              {DEMO_PERSONAS.map((p) => (
                <li key={p.id}>
                  <form action={demoSignIn.bind(null, p.id, safeNext)}>
                    <button className="group flex w-full items-center gap-4 rounded-ctl border border-line bg-bg px-4 py-3.5 text-left transition-[border-color,transform,background-color] hover:border-accent hover:bg-surface active:scale-[0.99]">
                      <span className="grid size-10 shrink-0 place-items-center rounded-full bg-accent-soft text-sm font-semibold text-accent">
                        {p.name.split(" ").map((x) => x[0]).join("")}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block font-medium">{p.name}</span>
                        <span className="block truncate text-sm text-muted">{p.role}. {p.blurb}</span>
                      </span>
                      <ArrowRight size={18} className="shrink-0 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-accent" />
                    </button>
                  </form>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <AuthForms next={safeNext} />
        )}
      </div>
    </div>
  );
}
