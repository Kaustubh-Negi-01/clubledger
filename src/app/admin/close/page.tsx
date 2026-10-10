import type { Metadata } from "next";
import { CheckCircle, LockKey, XCircle } from "@phosphor-icons/react/dist/ssr";
import { requireRole } from "@/lib/session";
import { rpc } from "@/lib/db";
import { dateTime, inr } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardHeader } from "@/components/ui/card";
import { ActionButton } from "@/components/ui/action-form";
import { closeTermAction, settleAction } from "@/app/actions/staff";

export const metadata: Metadata = { title: "Close the term" };

interface Status {
  term: { id: number; label: string; starts_at: string };
  checks: { code: string; label: string; ok: boolean; detail: string }[];
  snapshots: { term_id: number; label: string; taken_at: string; sha: string; totals: { watermark: number; accounts: Record<string, { name: string; opening: number; movement: number; closing: number }> } }[];
}

export default async function ClosePage() {
  await requireRole("/admin/close", "treasurer");
  const s = await rpc<Status>("api_close_status");
  const ready = s.checks.every((c) => c.ok);
  return (
    <>
      <PageHeader title="Close the term" description={`Closing ${s.term.label} seals a snapshot of the books, opens the next term and carries every balance forward. It cannot be undone.`} />
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <Card>
          <CardHeader title="Checklist" />
          <ul className="divide-y divide-line px-5 pb-2 pt-2">
            {s.checks.map((c) => (
              <li key={c.code} className="flex items-start gap-3 py-3.5">
                {c.ok ? <CheckCircle size={22} weight="fill" className="mt-0.5 shrink-0 text-ok" /> : <XCircle size={22} weight="fill" className="mt-0.5 shrink-0 text-bad" />}
                <div className="flex-1"><p className="font-medium">{c.label}</p><p className="num text-sm text-muted">{c.detail}</p></div>
                {!c.ok && c.code === "CLEARING" ? <ActionButton action={settleAction} variant="secondary">Pay out now</ActionButton> : null}
              </li>
            ))}
          </ul>
        </Card>
        <Card className="h-fit p-6">
          <LockKey size={28} className="text-accent" />
          <h2 className="mt-3 text-lg font-semibold tracking-tight">{ready ? "Ready to close" : "Not ready yet"}</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">{ready ? "Every check passes. Closing is one atomic step: the snapshot, the closed term and the new term are saved together or not at all." : "Fix the failing checks first. Nothing is written until all of them pass."}</p>
          <div className="mt-5">{ready ? <ActionButton action={closeTermAction} variant="primary" size="md" confirm={`Close ${s.term.label}? This cannot be undone.`}>Close {s.term.label}</ActionButton> : null}</div>
        </Card>
      </div>

      {s.snapshots.length ? (
        <section className="mt-12">
          <h2 className="mb-4 text-xl font-semibold tracking-tight">Sealed snapshots</h2>
          <div className="space-y-4">
            {s.snapshots.map((snap) => (
              <Card key={snap.term_id} className="p-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h3 className="text-lg font-semibold">{snap.label}</h3>
                  <p className="num text-xs text-muted" title="SHA-256 of the sealed totals">sealed {dateTime(snap.taken_at)}, sha256 {snap.sha.slice(0, 16)}</p>
                </div>
                <table className="num mt-4 w-full text-sm">
                  <thead><tr className="text-left text-xs text-muted"><th className="pb-2 font-medium">Account</th><th className="pb-2 text-right font-medium">Opening</th><th className="pb-2 text-right font-medium">Movement</th><th className="pb-2 text-right font-medium">Closing</th></tr></thead>
                  <tbody>
                    {Object.entries(snap.totals.accounts).filter(([, a]) => a.opening || a.movement || a.closing).map(([code, a]) => (
                      <tr key={code} className="border-t border-line"><td className="py-2 font-sans">{code} {a.name}</td><td className="py-2 text-right">{inr(a.opening)}</td><td className="py-2 text-right">{inr(a.movement, { signed: true })}</td><td className="py-2 text-right font-semibold">{inr(a.closing)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}
