import type { Metadata } from "next";
import Link from "next/link";
import { requireRole } from "@/lib/session";
import { rpc } from "@/lib/db";
import { dateTime, inr } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge, Badge } from "@/components/ui/badge";
import { ActionButton } from "@/components/ui/action-form";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { cn } from "@/lib/cn";
import { refundAction, resolveAction, settleAction } from "@/app/actions/staff";

export const metadata: Metadata = { title: "Payments" };

interface Row { id: string; purpose: string; amount_paise: number; status: string; fulfillment: string; created_at: string; settled_at: string | null; payer: string; email: string }

export default async function PaymentsPage({ searchParams }: { searchParams: Promise<{ problem?: string }> }) {
  const { problem } = await searchParams;
  await requireRole("/admin/payments", "treasurer");
  const rows = await rpc<Row[]>("api_payments_admin", { p_problem: !!problem });
  const unsettled = rows.filter((r) => r.status === "SUCCEEDED" && !r.settled_at);
  return (
    <>
      <PageHeader
        title="Payments"
        description="Money received sits in clearing until paid out to the bank. Payments that arrived after a reservation expired are never lost: they wait here until you refund or complete them."
        actions={<ActionButton action={settleAction} variant="primary" size="md">Pay out {unsettled.length} to the bank</ActionButton>}
      />
      <div className="mb-5 flex gap-2 text-sm">
        <Link href="/admin/payments" className={cn("rounded-full px-4 py-2", !problem ? "bg-ink text-bg" : "bg-surface-2 text-muted hover:text-ink")}>All</Link>
        <Link href="/admin/payments?problem=1" className={cn("rounded-full px-4 py-2", problem ? "bg-ink text-bg" : "bg-surface-2 text-muted hover:text-ink")}>Needs resolving</Link>
      </div>
      <TableWrap>
        <Table>
          <thead><tr><Th>Payer</Th><Th>For</Th><Th align="right">Amount</Th><Th>Status</Th><Th>Banked</Th><Th /></tr></thead>
          <tbody>
            {rows.map((r) => (
              <Tr key={r.id}>
                <Td><p className="font-medium">{r.payer}</p><p className="text-xs text-muted">{dateTime(r.created_at)}</p></Td>
                <Td className="capitalize">{r.purpose.toLowerCase()}</Td>
                <Td align="right" num>{inr(r.amount_paise)}</Td>
                <Td><div className="flex flex-wrap gap-1.5"><StatusBadge status={r.status} />{r.fulfillment === "UNFULFILLED" ? <StatusBadge status="UNFULFILLED" /> : null}</div></Td>
                <Td className="text-sm text-muted">{r.settled_at ? dateTime(r.settled_at) : r.status === "SUCCEEDED" ? <Badge tone="warn">In clearing</Badge> : ""}</Td>
                <Td align="right">
                  <div className="flex justify-end gap-1.5">
                    {r.status === "SUCCEEDED" && r.fulfillment === "UNFULFILLED" ? (
                      <>
                        <ActionButton action={resolveAction.bind(null, r.id, "FULFILL")} variant="primary">Complete order</ActionButton>
                        <ActionButton action={resolveAction.bind(null, r.id, "REFUND")} variant="secondary" confirm="Refund this payment in full?">Refund</ActionButton>
                      </>
                    ) : r.status === "SUCCEEDED" ? (
                      <ActionButton action={refundAction.bind(null, r.id)} variant="ghost" confirm="Refund this payment in full? The ledger is reversed and the purchase is cancelled.">Refund</ActionButton>
                    ) : null}
                  </div>
                </Td>
              </Tr>
            ))}
            {rows.length === 0 ? <Tr><Td className="py-10 text-center text-muted" >{problem ? "Nothing needs resolving." : "No payments yet."}</Td><Td /><Td /><Td /><Td /><Td /></Tr> : null}
          </tbody>
        </Table>
      </TableWrap>
    </>
  );
}
