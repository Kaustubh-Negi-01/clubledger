import { Media } from "@/components/media";
import Link from "next/link";
import { ArrowRight, ArrowUpRight, Check, EnvelopeSimple, MapPin } from "@phosphor-icons/react/dist/ssr";
import { rpc } from "@/lib/db";
import { getMe } from "@/lib/session";
import { dayParts, inr } from "@/lib/format";
import type { EventRow, Product } from "@/lib/types";
import { Button, buttonClass } from "@/components/ui/button";
import { Qr } from "@/components/qr";
import { HeroPass } from "@/components/landing/hero-pass";
import { Reveal } from "@/components/landing/reveal";
import { CountUp } from "@/components/landing/count-up";
import { Story } from "@/components/landing/story";
import { DoorDemo } from "@/components/landing/door-demo";
import { SubscribeForm } from "@/components/subscribe-form";
import { cn } from "@/lib/cn";

interface Stats { members: number; events: number; tickets: number; orders: number }

export default async function Home() {
  const [events, products, stats, me] = await Promise.all([
    rpc<EventRow[]>("api_events_list").catch(() => []),
    rpc<Product[]>("api_products_list").catch(() => []),
    rpc<Stats>("api_public_stats").catch(() => ({ members: 0, events: 0, tickets: 0, orders: 0 })),
    getMe(),
  ]);
  const upcoming = events.filter((e) => e.status === "ON_SALE").sort((a, b) => +new Date(a.starts_at) - +new Date(b.starts_at));
  const feature =
    [...upcoming].filter((e) => e.member_price_paise < e.public_price_paise).sort((a, b) => b.public_price_paise - a.public_price_paise)[0] ?? upcoming[0];
  const member = me?.membership?.status === "ACTIVE";
  const fp = feature ? dayParts(feature.starts_at) : null;

  return (
    <>
      {/* HERO: asymmetric split. Copy left, interactive pass right. */}
      <section className="relative overflow-hidden">
        <div aria-hidden className="pointer-events-none absolute -right-40 -top-40 size-[44rem] rounded-full bg-accent/10 blur-3xl" />
        <div className="mx-auto grid min-h-[calc(100dvh-4rem)] max-w-7xl items-center gap-12 px-4 pb-16 pt-10 sm:px-6 lg:grid-cols-[1.1fr_0.9fr] lg:pt-6">
          <div>
            <h1 className="display rise text-5xl sm:text-6xl lg:text-[5.4rem]" style={{ "--i": 0 } as React.CSSProperties}>
              Run the club.
              <br />
              <span className="text-accent">Skip the spreadsheet.</span>
            </h1>
            <p className="rise pretty-text mt-7 max-w-[34rem] text-lg leading-relaxed text-muted" style={{ "--i": 1 } as React.CSSProperties}>
              Skyline Student Association now signs members, sells tickets, ships merch and closes its books on one platform.
            </p>
            <div className="rise mt-9 flex flex-wrap items-center gap-3" style={{ "--i": 2 } as React.CSSProperties}>
              <Button href={member ? "/events" : "/join"} size="lg">
                {member ? "Browse events" : "Join the club"} <ArrowRight size={18} weight="bold" />
              </Button>
              <Button href={member ? "/me" : "/events"} variant="secondary" size="lg">
                {member ? "Open my club" : "See what is on"}
              </Button>
            </div>
          </div>
          <div className="rise" style={{ "--i": 2 } as React.CSSProperties}>
            <HeroPass
              title={feature?.title ?? "Spring Gala"}
              when={fp ? `${fp.weekday}, ${fp.day} ${fp.month} at ${fp.time}` : "Saturday evening"}
              where={feature?.venue ?? "Skyline Grand Hall"}
              member={feature ? inr(feature.member_price_paise) : "₹650"}
              pub={feature ? inr(feature.public_price_paise) : "₹950"}
              code="7K2Q 9M4D X81B"
              image={feature?.image_url ?? null}
              qr={<Qr value="CL-T:SAMPLE-7K2Q9M4DX81B" label="Sample ticket QR code" className="text-black" />}
            />
          </div>
        </div>
      </section>

      {/* LIVE NUMBERS: straight from the database. */}
      <section aria-label="The club in numbers" className="border-y border-line bg-surface">
        <dl className="mx-auto grid max-w-7xl grid-cols-2 gap-y-8 px-4 py-10 sm:px-6 md:grid-cols-4">
          {[
            [stats.members, "active members"],
            [stats.events, "events run"],
            [stats.tickets, "tickets issued"],
            [stats.orders, "merch orders filled"],
          ].map(([v, l], i) => (
            <Reveal key={l as string} delay={i * 0.07} className={cn("px-2 md:px-8", i > 0 && "md:border-l md:border-line")}>
              <dd className="display text-5xl md:text-6xl"><CountUp value={v as number} /></dd>
              <dt className="mt-2 text-[15px] text-muted">{l}</dt>
            </Reveal>
          ))}
        </dl>
      </section>

      {/* EVENTS RAIL: horizontal scroll-snap. */}
      <section className="py-24">
        <div className="mx-auto flex max-w-7xl items-end justify-between gap-4 px-4 sm:px-6">
          <Reveal>
            <h2 className="display text-4xl md:text-5xl">What is on.</h2>
          </Reveal>
          <Link href="/events" className="group inline-flex items-center gap-1.5 text-[15px] font-medium">
            All events <ArrowUpRight size={18} className="transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </Link>
        </div>
        <div className="scrollbar-none mt-10 flex snap-x snap-mandatory gap-5 overflow-x-auto px-4 pb-4 sm:px-6 lg:pl-[max(1.5rem,calc((100vw-80rem)/2+1.5rem))]">
          {upcoming.map((e) => {
            const p = dayParts(e.starts_at);
            const free = e.public_price_paise === 0;
            return (
              <Link key={e.id} href={`/events/${e.id}`} className="group w-[19rem] shrink-0 snap-start sm:w-[22rem]">
                <article className="overflow-hidden rounded-card border border-line bg-surface shadow-card transition-transform duration-500 ease-out group-hover:-translate-y-1.5">
                  <div className="relative aspect-[4/3] overflow-hidden">
                    <Media src={e.image_url} title={e.title} sizes="22rem" className="transition-transform duration-700 group-hover:scale-105" />
                    <div className="absolute left-4 top-4 rounded-xl bg-bg/90 px-3 py-2 text-center backdrop-blur">
                      <p className="num text-xl font-semibold leading-none">{p.day}</p>
                      <p className="mt-1 text-xs uppercase tracking-wide text-muted">{p.month}</p>
                    </div>
                  </div>
                  <div className="space-y-3 p-5">
                    <h3 className="text-xl font-semibold tracking-tight">{e.title}</h3>
                    <p className="flex items-center gap-1.5 text-sm text-muted"><MapPin size={16} /> {e.venue}</p>
                    <div className="flex items-end justify-between pt-1">
                      <div>
                        {free ? <p className="num text-lg font-semibold">Free entry</p> : (
                          <p className="num text-lg font-semibold">{inr(e.member_price_paise)} <span className="text-sm font-normal text-muted">members</span></p>
                        )}
                        {!free && e.public_price_paise !== e.member_price_paise ? <p className="num text-sm text-muted">{inr(e.public_price_paise)} public</p> : null}
                      </div>
                      <span className={cn("rounded-full px-2.5 py-1 text-xs font-medium", e.available <= 10 ? "bg-warn-soft text-warn" : "bg-surface-2 text-muted")}>
                        {e.available === 0 ? "Sold out" : `${e.available} left`}
                      </span>
                    </div>
                  </div>
                </article>
              </Link>
            );
          })}
        </div>
      </section>

      {/* BENTO: exactly four cells. */}
      <section className="mx-auto max-w-7xl px-4 pb-24 sm:px-6">
        <Reveal>
          <h2 className="display max-w-3xl text-4xl md:text-5xl">Membership that pays for itself by the second event.</h2>
        </Reveal>
        <div className="mt-12 grid gap-5 md:grid-cols-6 md:grid-rows-[auto_auto_auto]">
          <Reveal className="relative overflow-hidden rounded-card bg-accent p-8 text-accent-ink md:col-span-4 md:row-span-2 md:p-10">
            <div aria-hidden className="absolute -bottom-24 -right-16 size-80 rounded-full bg-black/10" />
            <p className="max-w-xs text-lg font-medium opacity-90">Gala ticket</p>
            <div className="mt-8 flex flex-wrap items-end gap-x-6 gap-y-2">
              <span className="num display text-7xl md:text-8xl">{feature ? inr(feature.member_price_paise) : "₹650"}</span>
              <span className="num pb-3 text-2xl line-through opacity-70">{feature ? inr(feature.public_price_paise) : "₹950"}</span>
            </div>
            <ul className="mt-10 grid gap-3 text-[17px] sm:grid-cols-2">
              {["Cheaper tickets at every event", "10% off all merchandise", "A QR member card for the door", "Renewal reminders, never a lapse"].map((t) => (
                <li key={t} className="flex items-start gap-2.5"><Check size={20} weight="bold" className="mt-0.5 shrink-0" />{t}</li>
              ))}
            </ul>
            <Link href="/join" className={buttonClass("secondary", "md", "mt-10 border-transparent bg-white text-black hover:bg-white/90")}>Become a member</Link>
          </Reveal>

          <Reveal delay={0.08} className="group relative min-h-64 overflow-hidden rounded-card md:col-span-2">
            <Media src={products[0]?.image_url} quiet title={products[0]?.name ?? "Skyline Hoodie"} sizes="(min-width:768px) 30vw, 100vw" className="transition-transform duration-700 group-hover:scale-105" />
            <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/10 to-transparent" />
            <div className="absolute inset-x-6 bottom-6 text-white">
              <p className="text-2xl font-semibold tracking-tight">{products[0]?.name ?? "Skyline Hoodie"}</p>
              <p className="num mt-1 text-white/80">{products[0] ? inr(products[0].my_price) : "₹1,499"}, sized and reserved</p>
            </div>
          </Reveal>

          <Reveal delay={0.16} className="rounded-card bg-[#12151c] p-7 text-white md:col-span-2">
            <DoorDemo />
          </Reveal>

          <Reveal delay={0.1} className="rounded-card border border-line bg-surface p-8 md:col-span-6 md:p-10">
            <div className="grid gap-8 md:grid-cols-[1fr_1.2fr] md:items-center">
              <div>
                <h3 className="display text-3xl md:text-4xl">Books anyone on the team can read.</h3>
                <p className="mt-4 max-w-md text-[17px] leading-relaxed text-muted">Every rupee in is an entry. Every refund reverses it exactly. Posted entries can never be edited.</p>
              </div>
              <div className="num divide-y divide-line rounded-ctl border border-line bg-bg text-[15px]">
                {[["Ticket income", "+₹1,82,000"], ["Dues income", "+₹45,000"], ["Merchandise income", "+₹3,24,000"], ["Reimbursement paid", "-₹5,430"]].map(([k, v]) => (
                  <div key={k} className="flex justify-between px-5 py-3.5"><span className="font-sans text-muted">{k}</span><span className={v.startsWith("-") ? "text-bad" : ""}>{v}</span></div>
                ))}
                <div className="flex justify-between bg-surface-2 px-5 py-3.5 font-semibold"><span className="font-sans">Left in the account</span><span>{"₹"}5,45,570</span></div>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* STORY: scroll-pinned walk through a semester. */}
      <section className="border-y border-line bg-surface/60">
        <Story />
      </section>

      {/* MERCH */}
      {products.length ? (
        <section className="mx-auto max-w-7xl px-4 py-24 sm:px-6">
          <div className="flex items-end justify-between gap-4">
            <Reveal><h2 className="display text-4xl md:text-5xl">Wear the crest.</h2></Reveal>
            <Link href="/store" className="group inline-flex items-center gap-1.5 text-[15px] font-medium">Open the store <ArrowUpRight size={18} className="transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" /></Link>
          </div>
          <div className="mt-10 grid gap-5 sm:grid-cols-3">
            {products.slice(0, 3).map((p, i) => (
              <Reveal key={p.id} delay={i * 0.08}>
                <Link href="/store" className="group block">
                  <div className="relative aspect-[4/5] overflow-hidden rounded-card bg-surface-2">
                    <Media src={p.image_url} title={p.name} sizes="(min-width:640px) 30vw, 100vw" className="transition-transform duration-700 group-hover:scale-105" />
                  </div>
                  <div className="mt-4 flex items-baseline justify-between gap-3">
                    <h3 className="text-lg font-semibold tracking-tight">{p.name}</h3>
                    <p className="num">{inr(p.my_price)}</p>
                  </div>
                </Link>
              </Reveal>
            ))}
          </div>
        </section>
      ) : null}

      {/* SUBSCRIBE */}
      <section className="mx-auto max-w-7xl px-4 pb-8 sm:px-6">
        <Reveal className="grid gap-8 rounded-card border border-line bg-surface p-8 shadow-card md:grid-cols-2 md:items-center md:p-12">
          <div>
            <h2 className="display text-3xl md:text-4xl">One announcement. Everyone hears it.</h2>
            <p className="mt-4 max-w-md text-[17px] leading-relaxed text-muted">Meeting times, deadlines and changes of plan, by email. Unsubscribe in one click.</p>
          </div>
          <div className="space-y-3">
            <SubscribeForm />
            <p className="flex items-center gap-2 text-sm text-muted"><EnvelopeSimple size={16} /> Every message is kept in the club&apos;s announcement history.</p>
          </div>
        </Reveal>
      </section>
    </>
  );
}
