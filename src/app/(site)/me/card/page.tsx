import type { Metadata } from "next";
import { requireMe } from "@/lib/session";
import { validThrough } from "@/lib/format";
import { Qr } from "@/components/qr";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";

export const metadata: Metadata = { title: "Member card" };

export default async function CardPage() {
  const me = await requireMe("/me/card");
  const m = me.membership;
  const active = m?.status === "ACTIVE" && !!m.qr_token;

  if (!m || !active)
    return (
      <div className="mx-auto max-w-md space-y-5 py-10 text-center">
        <h1 className="display text-4xl">No active card.</h1>
        <p className="text-muted">{m?.status === "PENDING" ? "Your dues payment is still pending." : m?.status === "EXPIRED" ? "Your membership expired. Renew to get a new card." : "Join the club to get a member card with a QR code."}</p>
        <Button href="/join">{m?.status === "EXPIRED" ? "Renew membership" : "Join the club"}</Button>
      </div>
    );

  return (
    <div className="mx-auto max-w-md py-4">
      <div className="stub relative overflow-hidden rounded-[26px] bg-[#12151c] p-8 text-white shadow-card [--notch-y:62%] [--notch:14px]">
        <div aria-hidden className="absolute -right-20 -top-20 size-64 rounded-full bg-accent/30 blur-3xl" />
        <div className="relative flex items-start justify-between">
          <div>
            <p className="text-sm text-white/60">Skyline Student Association</p>
            <p className="mt-6 text-3xl font-semibold tracking-tight">{me.name}</p>
            <p className="mt-1 text-white/60">{m.plan_name}</p>
          </div>
          <StatusBadge status={m.status} />
        </div>
        <div className="relative mt-8 flex justify-center rounded-2xl bg-white p-5 text-black">
          <Qr value={`CL-M:${m.qr_token}`} label="Your member QR code" className="w-full max-w-[14rem]" />
        </div>
        <div className="perforation relative mt-8 h-[2px] opacity-40" />
        <dl className="relative mt-6 grid grid-cols-2 gap-4 text-sm">
          <div><dt className="text-white/60">Member code</dt><dd className="num mt-1 text-lg font-semibold tracking-wider">{m.member_code}</dd></div>
          <div className="text-right"><dt className="text-white/60">Valid through</dt><dd className="mt-1 text-lg font-semibold">{validThrough(m.expires_at)}</dd></div>
        </dl>
      </div>
      <p className="mt-6 text-center text-sm text-muted">Staff see your name and whether you are a member. Nothing else.</p>
    </div>
  );
}
