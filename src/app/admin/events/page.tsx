import type { Metadata } from "next";
import Link from "next/link";
import { Plus } from "@phosphor-icons/react/dist/ssr";
import { requireRole } from "@/lib/session";
import { rpc } from "@/lib/db";
import { dateTime, inr } from "@/lib/format";
import type { EventRow } from "@/lib/types";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";

export const metadata: Metadata = { title: "Manage events" };

export default async function AdminEvents() {
  await requireRole("/admin/events", "organizer");
  const events = (await rpc<EventRow[]>("api_events_list", { p_all: true })).sort((a, b) => +new Date(b.starts_at) - +new Date(a.starts_at));
  return (
    <>
      <PageHeader title="Events" description="Create events, set member and public prices, open sales and watch the seats fill." actions={<Button href="/admin/events/new"><Plus size={18} /> New event</Button>} />
      <TableWrap>
        <Table>
          <thead><tr><Th>Event</Th><Th>When</Th><Th>Status</Th><Th align="right">Member / public</Th><Th align="right">Sold</Th><Th align="right">Checked in</Th></tr></thead>
          <tbody>
            {events.map((e) => (
              <Tr key={e.id}>
                <Td><Link href={`/admin/events/${e.id}`} className="font-medium hover:text-accent">{e.title}</Link><p className="text-sm text-muted">{e.venue}</p></Td>
                <Td>{dateTime(e.starts_at)}</Td>
                <Td><StatusBadge status={e.status} /></Td>
                <Td align="right" num>{inr(e.member_price_paise)} / {inr(e.public_price_paise)}</Td>
                <Td align="right" num>{e.sold ?? 0}/{e.capacity}</Td>
                <Td align="right" num>{e.attended ?? 0}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </TableWrap>
    </>
  );
}
