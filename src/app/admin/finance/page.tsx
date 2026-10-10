import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle, XCircle } from "@phosphor-icons/react/dist/ssr";
import { requireRole } from "@/lib/session";
import { rpc } from "@/lib/db";
import { dateTime, inr } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import { AdjustmentForm } from "./adjustment";

export const metadata: Metadata = { title: "Finance" };

interface Summary {
  term: { id: number; label: string; starts_at: string };
  cash: { cash_on_hand: number; in_clearing: number; unfulfilled: number; reimbursements_payable: number };
  income: { code: string; name: string; amount: number }[];
  expenses: { code: string; name: string; amount: number }[];
  adjustments: { id: number; memo: string; adjusts_term_id: number }[];
}
interface Entry { id: number; entry_date: string; source_type: string; source_event: string; memo: string | null; reverses_entry_id: number | null; adjusts_term_id: number | null; lines: { account: string; name: string; debit: number; credit: number }[] }
interface Check { name: string; ok: boolean; detail: string }

export default async function FinancePage({ searchParams }: { searchParams: Promise<{ account?: string }> }) {
  const { account } = await searchParams;
  await requireRole("/admin/finance", "treasurer");
  const [s, entries, checks, closed] = await Promise.all([
    rpc<Summary>("api_finance_summary"),
    rpc<Entry[]>("api_ledger", { p_account: account ?? null, p_limit: 60 }),
    rpc<Check[]>("api_integrity"),
    rpc<{ snapshots: { term_id: number; label: string }[] }>("api_close_status"),
  ]);
  const income = s.income.reduce((a, b) => a + b.amount, 0);
  const spent = s.expenses.reduce((a, b) => a + b.amount, 0);
  const net = income - spent;

  return (
    <>
      <PageHeader title="Finance" description={`${s.term.label}. Cash is the running balance across every term. Income and expenses are this term's activity only.`} />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Link href="/admin/finance?account=1000"><Card className="h-full p-5 hover:bg-surface-2"><p className="text-sm text-muted">Cash in the bank</p><p className="num display mt-2 text-4xl">{inr(s.cash.cash_on_hand)}</p></Card></Link>
        <Link href="/admin/finance?account=1100"><Card className="h-full p-5 hover:bg-surface-2"><p className="text-sm text-muted">Received, not yet banked</p><p className="num display mt-2 text-4xl">{inr(s.cash.in_clearing)}</p></Card></Link>
        <Link href="/admin/finance?account=2000"><Card className={cn("h-full p-5 hover:bg-surface-2", s.cash.unfulfilled && "border-bad/40")}><p className="text-sm text-muted">Owed for unfulfilled payments</p><p className="num display mt-2 text-4xl">{inr(s.cash.unfulfilled)}</p></Card></Link>
        <Link href="/admin/finance?account=2100"><Card className="h-full p-5 hover:bg-surface-2"><p className="text-sm text-muted">Reimbursements owed</p><p className="num display mt-2 text-4xl">{inr(s.cash.reimbursements_payable)}</p></Card></Link>
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Came in this term" action={<span className="num font-semibold">{inr(income)}</span>} />
          <ul className="px-5 pb-4 pt-2">
            {s.income.map((r) => (
              <li key={r.code} className="flex items-center justify-between border-b border-line py-3 last:border-0">
                <Link href={`/admin/finance?account=${r.code}`} className="hover:text-accent">{r.name}</Link><span className="num">{inr(r.amount)}</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <CardHeader title="Went out this term" action={<span className="num font-semibold">{inr(spent)}</span>} />
          <ul className="px-5 pb-4 pt-2">
            {s.expenses.map((r) => (
              <li key={r.code} className="flex items-center justify-between border-b border-line py-3 last:border-0">
                <Link href={`/admin/finance?account=${r.code}`} className="hover:text-accent">{r.name}</Link><span className="num">{inr(r.amount)}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      <p className="mt-4 text-[15px]">Net for the term: <span className={cn("num font-semibold", net < 0 && "text-bad")}>{inr(net, { signed: true })}</span></p>

      <section className="mt-12" aria-labelledby="ledger">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 id="ledger" className="text-xl font-semibold tracking-tight">Ledger {account ? <span className="text-muted">for account {account}</span> : null}</h2>
          {account ? <Link href="/admin/finance" className="text-sm font-medium text-accent">Show everything</Link> : null}
        </div>
        <div className="space-y-3">
          {entries.map((e) => (
            <Card key={e.id} className="p-4">
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <p><span className="num font-semibold">#{e.id}</span> <span className="text-muted">{dateTime(e.entry_date)}</span> <span className="ml-2">{e.memo ?? `${e.source_type} ${e.source_event}`}</span></p>
                <div className="flex gap-1.5">
                  {e.reverses_entry_id ? <Badge tone="warn">Reversal of #{e.reverses_entry_id}</Badge> : null}
                  {e.adjusts_term_id ? <Badge tone="info">Adjusts a closed term</Badge> : null}
                </div>
              </div>
              <table className="num mt-3 w-full text-sm">
                <tbody>
                  {e.lines.map((l, i) => (
                    <tr key={i} className="border-t border-line">
                      <td className="py-1.5 pr-3 text-muted">{l.account}</td>
                      <td className="py-1.5 font-sans">{l.name}</td>
                      <td className="py-1.5 text-right">{l.debit ? inr(l.debit) : ""}</td>
                      <td className="w-32 py-1.5 text-right">{l.credit ? inr(l.credit) : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          ))}
        </div>
        <p className="mt-3 text-xs text-muted">Debits on the left amount column, credits on the right. Posted entries can never be edited; refunds add an exact mirror entry.</p>
      </section>

      <div className="mt-12 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Books integrity" />
          <ul className="space-y-1 p-5 pt-3">
            {checks.map((c) => (
              <li key={c.name} className="flex items-start gap-3 py-1.5 text-[15px]">
                {c.ok ? <CheckCircle size={20} weight="fill" className="mt-0.5 shrink-0 text-ok" /> : <XCircle size={20} weight="fill" className="mt-0.5 shrink-0 text-bad" />}
                <span>{c.name} <span className="num text-xs text-muted">({c.detail})</span></span>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <CardHeader title="Correct a closed term" />
          <div className="p-5 pt-3">
            {closed.snapshots.length ? <AdjustmentForm terms={closed.snapshots.map((x) => ({ id: x.term_id, label: x.label }))} /> : <p className="text-sm leading-relaxed text-muted">Closed terms are never edited. Once you close one, corrections are posted here as balanced adjusting entries in the open term.</p>}
            {s.adjustments.length ? <p className="mt-4 text-sm text-muted">{s.adjustments.length} adjustment(s) this term.</p> : null}
          </div>
        </Card>
      </div>
    </>
  );
}
