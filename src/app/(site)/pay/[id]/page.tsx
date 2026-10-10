import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CheckCircle, Hourglass, LockSimple, WarningCircle, XCircle } from "@phosphor-icons/react/dist/ssr";
import { rpc } from "@/lib/db";
import { requireMe } from "@/lib/session";
import { inr } from "@/lib/format";
import type { Payment } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { ActionButton } from "@/components/ui/action-form";
import { payOutcomeAction } from "@/app/actions/member";
import { Countdown } from "./countdown";

export const metadata: Metadata = { title: "Checkout" };

const nextLink: Record<string, [string, string]> = {
  DUES: ["/me/card", "Open your member card"],
  TICKET: ["/me/tickets", "See your tickets"],
  MERCH: ["/me/orders", "See your order"],
};

export default async function PayPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await requireMe(`/pay/${id}`);
  const p = await rpc<Payment | null>("api_pay_get", { p_id: id }).catch(() => null);
  if (!p) notFound();

  return (
    <div className="mx-auto grid min-h-[calc(100dvh-8rem)] max-w-xl content-center px-4 py-12 sm:px-6">
      <div className="overflow-hidden rounded-card border border-line bg-surface shadow-card">
        <div className="space-y-1 border-b border-line p-7">
          <p className="text-sm text-muted">{p.purpose === "DUES" ? "Membership dues" : p.purpose === "TICKET" ? "Event tickets" : "Merchandise"}</p>
          <h1 className="text-2xl font-semibold tracking-tight">{p.title}</h1>
          {p.subtitle ? <p className="text-[15px] text-muted">{p.subtitle}</p> : null}
        </div>
        <div className="flex items-baseline justify-between p-7 pb-4">
          <span className="text-muted">Amount due</span>
          <span className="num display text-5xl">{inr(p.amount_paise)}</span>
        </div>

        {p.status === "CREATED" ? (
          <div className="space-y-4 p-7 pt-3">
            {p.hold_expires_at ? <Countdown until={p.hold_expires_at} /> : null}
            <ActionButton action={payOutcomeAction.bind(null, p.id, "success")} variant="primary" size="md" className="block [&_button]:h-[52px] [&_button]:w-full [&_button]:text-base">
              <LockSimple size={18} weight="bold" /> Pay {inr(p.amount_paise)}
            </ActionButton>
            <ActionButton action={payOutcomeAction.bind(null, p.id, "fail")} variant="ghost" size="md" className="block [&_button]:w-full">
              Simulate a declined payment
            </ActionButton>
            <p className="rounded-ctl bg-info-soft p-3.5 text-xs leading-relaxed text-info">
              This build uses a simulated gateway. Pressing pay marks the payment as received on the server. No real money moves. A live gateway (UPI or card) plugs in at this same step.
            </p>
          </div>
        ) : null}

        {p.status === "SUCCEEDED" && p.fulfillment === "FULFILLED" ? (
          <div className="space-y-5 p-7 pt-3">
            <div className="flex items-start gap-3 rounded-ctl bg-ok-soft p-4 text-ok">
              <CheckCircle size={26} weight="fill" className="shrink-0" />
              <div><p className="font-semibold">Payment received</p><p className="text-sm opacity-90">Everything is confirmed. It is already in the club&apos;s books.</p></div>
            </div>
            <Button href={nextLink[p.purpose][0]} size="lg" className="w-full">{nextLink[p.purpose][1]}</Button>
          </div>
        ) : null}

        {p.status === "SUCCEEDED" && p.fulfillment === "UNFULFILLED" ? (
          <div className="space-y-4 p-7 pt-3">
            <div className="flex items-start gap-3 rounded-ctl bg-warn-soft p-4 text-warn">
              <WarningCircle size={26} weight="fill" className="shrink-0" />
              <div>
                <p className="font-semibold">Payment received, but your reservation had expired</p>
                <p className="mt-1 text-sm leading-relaxed opacity-90">Your money is safe and recorded. The treasurer will either complete the order if seats or stock are free, or refund you in full.</p>
              </div>
            </div>
            <Button href="/me" variant="secondary" size="md" className="w-full">Back to my club</Button>
          </div>
        ) : null}

        {p.status === "REFUNDED" ? (
          <div className="space-y-4 p-7 pt-3">
            <div className="flex items-start gap-3 rounded-ctl bg-surface-2 p-4"><Hourglass size={26} className="shrink-0 text-muted" /><div><p className="font-semibold">Refunded in full</p><p className="text-sm text-muted">This payment was refunded and reversed in the books.</p></div></div>
          </div>
        ) : null}

        {p.status === "FAILED" || p.status === "EXPIRED" ? (
          <div className="space-y-4 p-7 pt-3">
            <div className="flex items-start gap-3 rounded-ctl bg-bad-soft p-4 text-bad">
              <XCircle size={26} weight="fill" className="shrink-0" />
              <div><p className="font-semibold">{p.status === "FAILED" ? "Payment did not go through" : "This checkout expired"}</p><p className="text-sm opacity-90">Nothing was charged. Start again from the event, store or membership page.</p></div>
            </div>
            <Link href={p.purpose === "DUES" ? "/join" : p.purpose === "TICKET" ? "/events" : "/store"} className="block text-center text-sm font-medium underline underline-offset-4">Start over</Link>
          </div>
        ) : null}
      </div>
    </div>
  );
}
