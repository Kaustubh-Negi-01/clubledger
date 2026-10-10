import type { Metadata } from "next";
import { Ticket as TicketIcon } from "@phosphor-icons/react/dist/ssr";
import { rpc } from "@/lib/db";
import { dateTime } from "@/lib/format";
import type { Ticket } from "@/lib/types";
import { Qr } from "@/components/qr";
import { Empty } from "@/components/ui/empty";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

export const metadata: Metadata = { title: "My tickets" };

export default async function TicketsPage({ searchParams }: { searchParams: Promise<{ new?: string }> }) {
  const { new: isNew } = await searchParams;
  const tickets = await rpc<Ticket[]>("api_my_tickets");
  const now = Date.now();
  const live = tickets.filter((t) => new Date(t.ends_at).getTime() >= now || t.status === "ISSUED");
  const rest = tickets.filter((t) => !live.includes(t));

  return (
    <div className="space-y-8">
      <div>
        <h1 className="display text-4xl">My tickets</h1>
        <p className="mt-3 text-muted">Show the QR code at the door. One ticket per seat, scanned once.</p>
      </div>
      {isNew ? <p role="status" className="rounded-ctl bg-ok-soft px-4 py-3 text-sm text-ok">Your free tickets are ready below.</p> : null}
      {tickets.length === 0 ? (
        <Empty icon={TicketIcon} title="No tickets yet">
          <p>Browse what is coming up and grab a seat.</p>
          <Button href="/events" size="sm" className="mt-4">See events</Button>
        </Empty>
      ) : null}
      <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
        {[...live, ...rest].map((t) => (
          <article key={t.id} className={cn("stub relative overflow-hidden rounded-[22px] border border-line bg-surface shadow-card [--notch-y:60%]", t.status !== "ISSUED" && "opacity-70")}>
            <div className="space-y-2 p-6 pb-5">
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-xl font-semibold tracking-tight">{t.title}</h2>
                <StatusBadge status={t.status} />
              </div>
              <p className="text-sm text-muted">{t.venue}</p>
              <p className="text-sm">{dateTime(t.starts_at)}</p>
            </div>
            <div className="perforation mx-6 h-[2px]" />
            <div className="flex items-center gap-5 p-6 pt-5">
              <div className="size-28 shrink-0 rounded-xl border border-line bg-white p-2.5 text-black">
                <Qr value={`CL-T:${t.code}`} label={`QR code for ${t.title}, seat ${t.seat_index}`} />
              </div>
              <div className="min-w-0">
                <p className="text-xs text-muted">Ticket code</p>
                <p className="num mt-1 truncate text-lg font-semibold tracking-wider">{t.code}</p>
                <p className="mt-2 text-xs text-muted">Seat {t.seat_index}, {t.price_tier === "MEMBER" ? "member price" : "public price"}</p>
                {t.used_at ? <p className="mt-1 text-xs text-muted">Scanned {dateTime(t.used_at)}</p> : null}
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
