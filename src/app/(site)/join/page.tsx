import type { Metadata } from "next";
import Link from "next/link";
import { Check, SealCheck } from "@phosphor-icons/react/dist/ssr";
import { rpc } from "@/lib/db";
import { getMe } from "@/lib/session";
import { validThrough, inr } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { SubmitButton } from "@/components/ui/action-form";
import { joinAction } from "@/app/actions/member";

export const metadata: Metadata = { title: "Join the club" };

interface Plan { id: number; name: string; dues_paise: number; ticket_discount_bps: number; merch_discount_bps: number; perks: string[] }

export default async function JoinPage() {
  const [plans, me] = await Promise.all([rpc<Plan[]>("api_plans"), getMe()]);
  const m = me?.membership;
  const active = m?.status === "ACTIVE";
  const renewable = active && m ? new Date(m.expires_at).getTime() - Date.now() < 30 * 86400_000 : false;

  return (
    <div className="mx-auto max-w-5xl px-4 py-14 sm:px-6">
      <h1 className="display max-w-3xl text-5xl md:text-7xl">One year of member prices.</h1>
      <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted">Membership runs on the academic year, 1 August to 31 July. Pay once, and every ticket and hoodie is cheaper until it ends.</p>

      {active && m ? (
        <div className="mt-10 flex flex-wrap items-center gap-4 rounded-card border border-ok/30 bg-ok-soft p-5 text-ok">
          <SealCheck size={28} weight="fill" />
          <p className="flex-1 text-[15px]">You are a member until <strong>{validThrough(m.expires_at)}</strong>.{renewable ? " You can renew now." : ""}</p>
          <Button href="/me/card" variant="secondary" size="sm">Open member card</Button>
        </div>
      ) : null}

      <div className="mt-12 grid gap-6 md:grid-cols-[1.2fr_0.8fr]">
        {plans.map((p) => (
          <div key={p.id} className="rounded-card border border-line bg-surface p-8 shadow-card md:col-span-1">
            <h2 className="text-lg font-semibold tracking-tight">{p.name}</h2>
            <p className="num display mt-4 text-6xl">{inr(p.dues_paise)}</p>
            <p className="mt-1 text-muted">for the academic year</p>
            <ul className="mt-8 space-y-3.5">
              {p.perks.map((perk) => (
                <li key={perk} className="flex items-start gap-3 text-[16px]"><Check size={20} weight="bold" className="mt-0.5 shrink-0 text-accent" />{perk}</li>
              ))}
            </ul>
            <div className="mt-9">
              {!me ? (
                <Button href="/login?next=/join" size="lg" className="w-full">Sign in to join</Button>
              ) : active && !renewable ? (
                <Button href="/me" variant="secondary" size="lg" className="w-full">You are all set</Button>
              ) : (
                <form action={joinAction.bind(null, p.id)}>
                  <SubmitButton size="lg" className="w-full" pendingLabel="One moment">{active ? "Renew membership" : "Pay dues and join"}</SubmitButton>
                </form>
              )}
            </div>
          </div>
        ))}
        <div className="rounded-card bg-accent p-8 text-accent-ink">
          <p className="text-lg font-semibold">What changes at the door</p>
          <p className="mt-4 leading-relaxed opacity-90">Your member card carries a QR code. Staff scan it, see your name and your status, and nothing else about you.</p>
          <Link href="/events" className="mt-8 inline-block font-medium underline underline-offset-4">See member prices on events</Link>
        </div>
      </div>
    </div>
  );
}
