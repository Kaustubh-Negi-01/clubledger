import type { Metadata } from "next";
import { requireRole } from "@/lib/session";
import { rpc } from "@/lib/db";
import { dateTime, inr } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge } from "@/components/ui/badge";
import { ActionButton } from "@/components/ui/action-form";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { pickupAction } from "@/app/actions/staff";

export const metadata: Metadata = { title: "Orders" };

interface Row { id: number; status: string; total_paise: number; price_tier: string; created_at: string; picked_up_at: string | null; buyer: string; email: string; items: { name: string; size: string; qty: number }[] }

export default async function AdminOrders() {
  await requireRole("/admin/orders", "store");
  const rows = await rpc<Row[]>("api_orders_admin");
  const waiting = rows.filter((r) => r.status === "PAID");
  return (
    <>
      <PageHeader title="Orders" description={`${waiting.length} paid order(s) waiting to be handed over. Handing over reduces physical stock.`} />
      <TableWrap>
        <Table>
          <thead><tr><Th>Order</Th><Th>Buyer</Th><Th>Items</Th><Th align="right">Total</Th><Th>Status</Th><Th /></tr></thead>
          <tbody>
            {rows.map((r) => (
              <Tr key={r.id}>
                <Td num>#{r.id}<p className="font-sans text-xs text-muted">{dateTime(r.created_at)}</p></Td>
                <Td><p className="font-medium">{r.buyer}</p><p className="text-sm text-muted">{r.email}</p></Td>
                <Td className="text-sm">{r.items.map((i) => `${i.name} ${i.size} x${i.qty}`).join(", ")}</Td>
                <Td align="right" num>{inr(r.total_paise)}</Td>
                <Td><StatusBadge status={r.status} /></Td>
                <Td align="right">{r.status === "PAID" ? <ActionButton action={pickupAction.bind(null, r.id)} variant="primary">Hand over</ActionButton> : r.picked_up_at ? <span className="text-sm text-muted">{dateTime(r.picked_up_at)}</span> : null}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </TableWrap>
    </>
  );
}
