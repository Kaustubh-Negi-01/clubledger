import type { Metadata } from "next";
import { CalendarX } from "@phosphor-icons/react/dist/ssr";
import { rpc } from "@/lib/db";
import type { EventRow } from "@/lib/types";
import { PageHeader } from "@/components/ui/page-header";
import { Empty } from "@/components/ui/empty";
import { EventCard } from "@/components/event-card";

export const metadata: Metadata = { title: "Events" };

export default async function EventsPage() {
  const events = await rpc<EventRow[]>("api_events_list");
  const now = Date.now();
  const upcoming = events.filter((e) => new Date(e.ends_at).getTime() >= now);
  const past = events.filter((e) => new Date(e.ends_at).getTime() < now).reverse();
  return (
    <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
      <PageHeader title="Events" description="Member prices apply automatically once your membership is active. Seats are limited and held for ten minutes while you pay." />
      {upcoming.length ? (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {upcoming.map((e, i) => (
            <EventCard key={e.id} e={e} priority={i < 3} />
          ))}
        </div>
      ) : (
        <Empty icon={CalendarX} title="No events on sale right now">New events appear here as soon as the organizers publish them.</Empty>
      )}
      {past.length ? (
        <>
          <h2 className="mb-6 mt-20 text-xl font-semibold tracking-tight">Past events</h2>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {past.map((e) => (
              <EventCard key={e.id} e={e} />
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
