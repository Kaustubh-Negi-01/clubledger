import type { Metadata } from "next";
import { rpc } from "@/lib/db";
import type { EventRow } from "@/lib/types";
import { PageHeader } from "@/components/ui/page-header";
import { Scanner } from "./scanner";

export const metadata: Metadata = { title: "Door check-in" };

export default async function CheckinPage({ searchParams }: { searchParams: Promise<{ event?: string }> }) {
  const { event } = await searchParams;
  const events = (await rpc<EventRow[]>("api_events_list", { p_all: true })).filter((e) => e.status === "ON_SALE" || e.status === "CLOSED");
  const upcomingFirst = [...events].sort((a, b) => Math.abs(+new Date(a.starts_at) - Date.now()) - Math.abs(+new Date(b.starts_at) - Date.now()));
  return (
    <>
      <PageHeader title="Door check-in" description="Scan a ticket or member card, or type the code. The first scan admits; a second scan is refused." />
      <Scanner events={upcomingFirst.map((e) => ({ id: e.id, title: e.title, sold: e.sold ?? 0, attended: e.attended ?? 0 }))} initialId={event ? Number(event) : upcomingFirst[0]?.id} />
    </>
  );
}
