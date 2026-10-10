import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "@phosphor-icons/react/dist/ssr";
import { requireRole } from "@/lib/session";
import { rpc } from "@/lib/db";
import { dateTime, inr } from "@/lib/format";
import type { EventRow } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/card";
import { StatusBadge, Badge } from "@/components/ui/badge";
import { ActionButton } from "@/components/ui/action-form";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { setEventStatusAction } from "@/app/actions/staff";
import { EventForm } from "../event-form";

export const metadata: Metadata = { title: "Event" };

interface Report { sold: number; attended: number; no_shows: number; gross_paise: number; refunded_paise: number; net_paise: number; member_tickets: number; public_tickets: number }
interface Attendee { id: number; code: string; seat_index: number; status: string; price_tier: string; used_at: string | null; holder: string; email: string }

export default async function AdminEventPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await requireRole(`/admin/events/${id}`, "organizer");
  if (id === "new")
    return (
      <>
        <Link href="/admin/events" className="mb-6 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink"><ArrowLeft size={16} /> All events</Link>
        <h1 className="display mb-8 text-3xl md:text-4xl">New event</h1>
        <EventForm />
      </>
    );
  const e = await rpc<EventRow | null>("api_event_get", { p_id: Number(id) });
  if (!e) notFound();
  const [report, attendees] = await Promise.all([rpc<Report>("api_event_report", { p_id: e.id }), rpc<Attendee[]>("api_event_attendees", { p_id: e.id })]);

  return (
    <>
      <Link href="/admin/events" className="mb-6 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink"><ArrowLeft size={16} /> All events</Link>
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-3"><h1 className="display text-3xl md:text-4xl">{e.title}</h1><StatusBadge status={e.status} /></div>
          <p className="mt-2 text-muted">{dateTime(e.starts_at)} at {e.venue}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {e.status === "DRAFT" || e.status === "CLOSED" ? <ActionButton action={setEventStatusAction.bind(null, e.id, "ON_SALE")} variant="primary" size="md">Open ticket sales</ActionButton> : null}
          {e.status === "ON_SALE" ? <ActionButton action={setEventStatusAction.bind(null, e.id, "CLOSED")} variant="secondary" size="md">Close sales</ActionButton> : null}
          {e.status !== "CANCELLED" ? <ActionButton action={setEventStatusAction.bind(null, e.id, "CANCELLED")} variant="danger" size="md" confirm="Cancel this event? Every paid order is refunded in full and free tickets are voided. This cannot be undone.">Cancel event</ActionButton> : null}
          <Link href={`/admin/checkin?event=${e.id}`} className="inline-flex h-11 items-center rounded-ctl border border-line px-5 text-[15px] font-medium hover:bg-surface-2">Open check-in</Link>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        {[["Sold", report.sold], ["Attended", report.attended], ["No-shows", report.no_shows], ["Net proceeds", inr(report.net_paise)], ["Refunded", inr(report.refunded_paise)]].map(([l, v]) => (
          <Card key={l as string} className="p-5"><p className="text-sm text-muted">{l}</p><p className="num display mt-2 text-3xl">{v}</p></Card>
        ))}
      </div>
      <p className="mt-3 text-sm text-muted">{report.member_tickets} member tickets, {report.public_tickets} public tickets. Proceeds come from ticket prices and reconcile to the ledger on the integrity check.</p>

      <div className="mt-10 grid gap-8 xl:grid-cols-[1.1fr_0.9fr]">
        <Card><CardHeader title="Details" /><div className="p-5"><EventForm event={e} /></div></Card>
        <div>
          <h2 className="mb-4 text-lg font-semibold tracking-tight">Ticket holders</h2>
          <TableWrap>
            <Table className="min-w-0">
              <thead><tr><Th>Holder</Th><Th>Seat</Th><Th>Status</Th></tr></thead>
              <tbody>
                {attendees.map((a) => (
                  <Tr key={a.id}><Td><p className="font-medium">{a.holder}</p><p className="num text-xs text-muted">{a.code}</p></Td><Td num>{a.seat_index}</Td><Td>{a.status === "ISSUED" ? <Badge tone="ok">Not yet in</Badge> : <StatusBadge status={a.status} />}</Td></Tr>
                ))}
                {attendees.length === 0 ? <Tr><Td className="text-muted">No tickets sold yet.</Td><Td /><Td /></Tr> : null}
              </tbody>
            </Table>
          </TableWrap>
        </div>
      </div>
    </>
  );
}
