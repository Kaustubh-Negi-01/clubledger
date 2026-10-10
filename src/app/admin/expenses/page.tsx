import type { Metadata } from "next";
import { FileText } from "@phosphor-icons/react/dist/ssr";
import { requireRole } from "@/lib/session";
import { rpc } from "@/lib/db";
import { dateTime, inr } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";
import { ActionButton } from "@/components/ui/action-form";
import { payExpenseAction } from "@/app/actions/staff";
import { DecideForm } from "./decide";

export const metadata: Metadata = { title: "Expenses" };

interface Row { id: number; amount_paise: number; description: string; status: string; decision_note: string | null; created_at: string; category: string; submitter: string; submitter_id: string; receipts: { id: number; name: string; mime: string }[] }

export default async function ExpensesAdmin() {
  const me = await requireRole("/admin/expenses", "treasurer");
  const rows = await rpc<Row[]>("api_expenses_admin");
  const order = { SUBMITTED: 0, APPROVED: 1, PAID: 2, REJECTED: 3, VOID: 4 } as Record<string, number>;
  rows.sort((a, b) => order[a.status] - order[b.status] || b.id - a.id);
  return (
    <>
      <PageHeader title="Expenses" description="Approve what volunteers spent, then pay them back. Payment needs at least one receipt, and you cannot approve your own claim." />
      <div className="space-y-4">
        {rows.map((x) => (
          <Card key={x.id} className="p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="max-w-xl">
                <p className="text-lg font-semibold tracking-tight">{x.description}</p>
                <p className="mt-1 text-sm text-muted">{x.submitter}, {x.category}, {dateTime(x.created_at)}</p>
              </div>
              <div className="flex items-center gap-3"><StatusBadge status={x.status} /><span className="num text-2xl font-semibold">{inr(x.amount_paise)}</span></div>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
              {x.receipts.length ? x.receipts.map((r) => (
                <a key={r.id} href={`/receipts/${r.id}`} className="inline-flex items-center gap-1.5 rounded-full bg-surface-2 px-3 py-1.5 hover:bg-line"><FileText size={16} /> {r.name}</a>
              )) : <span className="text-warn">No receipt attached yet</span>}
            </div>
            {x.decision_note ? <p className="mt-3 rounded-ctl bg-surface-2 p-3 text-sm text-muted">Note: {x.decision_note}</p> : null}
            {x.status === "SUBMITTED" ? (
              x.submitter_id === me.id ? <p className="mt-4 text-sm text-muted">This is your own claim. Another treasurer or admin has to review it.</p> : <DecideForm id={x.id} />
            ) : null}
            {x.status === "APPROVED" ? (
              <div className="mt-4"><ActionButton action={payExpenseAction.bind(null, x.id)} variant="primary" size="md">Pay {inr(x.amount_paise)} to {x.submitter.split(" ")[0]}</ActionButton></div>
            ) : null}
          </Card>
        ))}
        {rows.length === 0 ? <p className="text-muted">No expenses submitted.</p> : null}
      </div>
    </>
  );
}
