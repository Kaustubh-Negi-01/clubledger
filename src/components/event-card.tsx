import { Media } from "./media";
import Link from "next/link";
import { MapPin } from "@phosphor-icons/react/dist/ssr";
import { dayParts, inr } from "@/lib/format";
import type { EventRow } from "@/lib/types";
import { cn } from "@/lib/cn";

export function EventCard({ e, priority = false }: { e: EventRow; priority?: boolean }) {
  const p = dayParts(e.starts_at);
  const free = e.public_price_paise === 0;
  const past = new Date(e.ends_at) < new Date();
  return (
    <Link href={`/events/${e.id}`} className="group block">
      <article className="overflow-hidden rounded-card border border-line bg-surface shadow-card transition-transform duration-500 ease-out group-hover:-translate-y-1.5">
        <div className="relative aspect-[4/3] overflow-hidden bg-surface-2">
          <Media src={e.image_url} title={e.title} priority={priority} sizes="(min-width:1024px) 30vw, (min-width:640px) 45vw, 100vw" className={cn("transition-transform duration-700 group-hover:scale-105", past && "grayscale")} />
          <div className="absolute left-4 top-4 rounded-xl bg-bg/90 px-3 py-2 text-center backdrop-blur">
            <p className="num text-xl font-semibold leading-none">{p.day}</p>
            <p className="mt-1 text-xs uppercase tracking-wide text-muted">{p.month}</p>
          </div>
        </div>
        <div className="space-y-3 p-5">
          <h3 className="text-xl font-semibold tracking-tight">{e.title}</h3>
          <p className="flex items-center gap-1.5 text-sm text-muted">
            <MapPin size={16} /> {e.venue} <span aria-hidden>.</span> {p.time}
          </p>
          <div className="flex items-end justify-between pt-1">
            <div>
              {free ? (
                <p className="num text-lg font-semibold">Free entry</p>
              ) : (
                <>
                  <p className="num text-lg font-semibold">
                    {inr(e.my_price)} <span className="font-sans text-sm font-normal text-muted">{e.my_tier === "MEMBER" ? "your price" : e.member_price_paise < e.public_price_paise ? "public" : ""}</span>
                  </p>
                  {e.my_tier === "PUBLIC" && e.member_price_paise < e.public_price_paise ? (
                    <p className="num text-sm text-accent">{inr(e.member_price_paise)} for members</p>
                  ) : null}
                </>
              )}
            </div>
            <span className={cn("rounded-full px-2.5 py-1 text-xs font-medium", past ? "bg-surface-2 text-muted" : e.available === 0 ? "bg-bad-soft text-bad" : e.available <= 10 ? "bg-warn-soft text-warn" : "bg-surface-2 text-muted")}>
              {past ? "Ended" : e.available === 0 ? "Sold out" : `${e.available} left`}
            </span>
          </div>
        </div>
      </article>
    </Link>
  );
}
