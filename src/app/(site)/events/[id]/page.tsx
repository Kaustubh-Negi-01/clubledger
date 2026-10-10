import type { Metadata } from "next";
import { Media } from "@/components/media";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CalendarBlank, Clock, MapPin, SealCheck } from "@phosphor-icons/react/dist/ssr";
import { rpc } from "@/lib/db";
import { getMe } from "@/lib/session";
import { dateOnly, dayParts, inr } from "@/lib/format";
import type { EventRow } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TicketPanel } from "./ticket-panel";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const e = await rpc<EventRow | null>("api_event_get", { p_id: Number(id) }).catch(() => null);
  return { title: e?.title ?? "Event" };
}

export default async function EventPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const e = Number.isFinite(Number(id)) ? await rpc<EventRow | null>("api_event_get", { p_id: Number(id) }) : null;
  if (!e) notFound();
  const me = await getMe();
  const p = dayParts(e.starts_at);
  const ended = new Date(e.ends_at) < new Date();
  const saving = e.public_price_paise - e.member_price_paise;

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
      <div className="grid gap-10 lg:grid-cols-[1.25fr_0.75fr]">
        <div>
          <div className="relative aspect-[16/10] overflow-hidden rounded-card bg-surface-2">
            <Media src={e.image_url} title={e.title} priority sizes="(min-width:1024px) 60vw, 100vw" />
          </div>
          <div className="mt-8 flex flex-wrap items-center gap-2">
            {e.status === "CANCELLED" ? <Badge tone="bad">Cancelled</Badge> : ended ? <Badge>Ended</Badge> : e.available === 0 ? <Badge tone="bad">Sold out</Badge> : <Badge tone="ok">On sale</Badge>}
            {e.status === "DRAFT" ? <Badge tone="warn">Draft, not public</Badge> : null}
          </div>
          <h1 className="display mt-4 text-4xl md:text-6xl">{e.title}</h1>
          <dl className="mt-8 grid gap-4 text-[15px] sm:grid-cols-3">
            <div className="flex items-start gap-3"><CalendarBlank size={22} className="mt-0.5 text-accent" /><div><dt className="text-muted">Date</dt><dd className="font-medium">{p.weekday}, {dateOnly(e.starts_at)}</dd></div></div>
            <div className="flex items-start gap-3"><Clock size={22} className="mt-0.5 text-accent" /><div><dt className="text-muted">Starts</dt><dd className="font-medium">{p.time}</dd></div></div>
            <div className="flex items-start gap-3"><MapPin size={22} className="mt-0.5 text-accent" /><div><dt className="text-muted">Venue</dt><dd className="font-medium">{e.venue}</dd></div></div>
          </dl>
          <p className="pretty-text mt-8 max-w-[65ch] text-[17px] leading-relaxed text-muted">{e.description}</p>
        </div>

        <aside className="lg:sticky lg:top-24 lg:self-start">
          <Card className="overflow-hidden">
            <div className="space-y-5 p-6">
              <div>
                <p className="text-sm text-muted">{e.my_tier === "MEMBER" ? "Your member price" : "Ticket price"}</p>
                <p className="num display mt-1 text-5xl">{e.my_price === 0 ? "Free" : inr(e.my_price)}</p>
                {e.my_tier === "MEMBER" && saving > 0 ? (
                  <p className="mt-2 flex items-center gap-1.5 text-sm text-ok"><SealCheck size={18} weight="fill" /> You save {inr(saving)} per ticket as a member</p>
                ) : null}
                {e.my_tier === "PUBLIC" && saving > 0 ? (
                  <p className="mt-2 text-sm text-muted">Members pay <span className="num font-medium text-accent">{inr(e.member_price_paise)}</span>. <Link href="/join" className="font-medium text-ink underline underline-offset-4">Join the club</Link></p>
                ) : null}
              </div>
              {e.status === "ON_SALE" && !ended ? (
                me ? (
                  <TicketPanel eventId={e.id} available={e.available} max={e.max_per_order} unit={e.my_price} />
                ) : (
                  <Button href={`/login?next=${encodeURIComponent(`/events/${e.id}`)}`} size="lg" className="w-full">Sign in to get tickets</Button>
                )
              ) : (
                <p className="rounded-ctl bg-surface-2 p-3.5 text-sm text-muted">Tickets are not on sale for this event.</p>
              )}
            </div>
            <div className="border-t border-line bg-surface-2 px-6 py-4 text-sm text-muted">
              <span className="num font-medium text-ink">{e.available}</span> of <span className="num">{e.capacity}</span> seats left. Up to {e.max_per_order} per order.
            </div>
          </Card>
        </aside>
      </div>
    </div>
  );
}
