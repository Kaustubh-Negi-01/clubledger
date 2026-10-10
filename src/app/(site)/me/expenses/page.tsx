import type { Metadata } from "next";
import { Receipt } from "@phosphor-icons/react/dist/ssr";
import { rpc } from "@/lib/db";
import { dateTime, inr } from "@/lib/format";
import type { EventRow, Fundraiser } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/card";
import { Empty } from "@/components/ui/empty";
import { StatusBadge } from "@/components/ui/badge";
import { ExpenseForm, ReceiptUpload } from "./forms";

export const metadata: Metadata = { title: "My expenses" };

interface Exp { id: number; amount_paise: number; description: string; status: string; decision_note: string | null; created_at: string; category: string; receipts: number }

export default async function ExpensesPage() {
  const [items, fundraisers, events] = await Promise.all([
    rpc<Exp[]>("api_my_expenses"),
    rpc<Fundraiser[]>("api_fundraisers"),
    rpc<EventRow[]>("api_events_list"),
  ]);
  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_24rem]">
      <div className="space-y-6">
        <div>
          <h1 className="display text-4xl">Expenses</h1>
          <p className="mt-3 max-w-[60ch] text-muted">Paid for something on the club&apos;s behalf? Submit it with the receipt. The treasurer approves it and the reimbursement is paid and booked.</p>
        </div>
        {items.length === 0 ? (
          <Empty icon={Receipt} title="Nothing submitted yet">Your submissions and their status show up here.</Empty>
        ) : (
          <ul className="space-y-4">
            {items.map((x) => (
              <Card key={x.id} className="p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold">{x.description}</p>
                    <p className="mt-1 text-sm text-muted">{x.category}, {dateTime(x.created_at)}</p>
                  </div>
                  <div className="flex items-center gap-3"><StatusBadge status={x.status} /><span className="num text-lg font-semibold">{inr(x.amount_paise)}</span></div>
                </div>
                {x.decision_note ? <p className="mt-3 rounded-ctl bg-surface-2 p-3 text-sm text-muted">Treasurer: {x.decision_note}</p> : null}
                <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
                  <span className={x.receipts ? "text-ok" : "text-warn"}>{x.receipts ? `${x.receipts} receipt${x.receipts > 1 ? "s" : ""} attached` : "No receipt yet. It cannot be paid without one."}</span>
                  {["SUBMITTED", "APPROVED"].includes(x.status) ? <ReceiptUpload expenseId={x.id} /> : null}
                </div>
              </Card>
            ))}
          </ul>
        )}
      </div>
      <Card className="h-fit lg:sticky lg:top-24">
        <CardHeader title="Submit an expense" />
        <div className="p-5">
          <ExpenseForm fundraisers={fundraisers.map((f) => ({ id: f.id, title: f.title }))} events={events.map((e) => ({ id: e.id, title: e.title }))} />
        </div>
      </Card>
    </div>
  );
}
