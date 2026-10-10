"use client";

import { AnimatePresence, motion, useMotionValueEvent, useReducedMotion, useScroll } from "motion/react";
import { useRef, useState } from "react";
import { Bag, Broadcast, CheckCircle, IdentificationCard, Receipt, Ticket, Users } from "@phosphor-icons/react";
import { cn } from "@/lib/cn";

const steps = [
  { icon: IdentificationCard, title: "A student joins", body: "Sign up, pay dues, and the member card appears with a QR code. Renewal reminders go out before it lapses." },
  { icon: Ticket, title: "The gala sells out fairly", body: "Member and public prices, a hard seat limit, and a ticket check-in that takes a second at the door." },
  { icon: Broadcast, title: "One announcement, everyone hears", body: "Post once. It reaches the website and the mailing list, and the history stays on record." },
  { icon: Bag, title: "Hoodies, by size", body: "Carts reserve stock for the whole order or not at all, so nobody pays for a size that is gone." },
  { icon: Users, title: "A bake sale, split up", body: "Every task has an owner, a date and a status, with the spend tracked against the goal." },
  { icon: Receipt, title: "The treasurer closes the books", body: "Income, expenses and cash on hand in one ledger, locked into a snapshot at the end of the term." },
];

export function Story() {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  const [active, setActive] = useState(0);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });
  useMotionValueEvent(scrollYProgress, "change", (v) => {
    const i = Math.min(steps.length - 1, Math.max(0, Math.floor(v * steps.length)));
    setActive((cur) => (cur === i ? cur : i));
  });

  return (
    <div ref={ref} className="relative" style={{ height: `${steps.length * 62}vh` }}>
      <div className="sticky top-0 flex min-h-[100dvh] items-center py-20">
        <div className="mx-auto grid w-full max-w-7xl items-center gap-10 px-4 sm:px-6 lg:grid-cols-[1fr_1.05fr]">
          <div>
            <h2 className="display text-4xl md:text-6xl">A semester, start to finish.</h2>
            <ol className="mt-10 space-y-1">
              {steps.map((s, i) => {
                const on = i === active;
                return (
                  <li key={s.title}>
                    <button
                      onClick={() => setActive(i)}
                      aria-current={on ? "step" : undefined}
                      className={cn(
                        "group flex w-full items-start gap-4 rounded-ctl px-4 py-3 text-left transition-[background-color,opacity] duration-300",
                        on ? "bg-surface shadow-card" : "opacity-55 hover:opacity-90",
                      )}
                    >
                      <span className={cn("mt-0.5 grid size-9 shrink-0 place-items-center rounded-full transition-colors", on ? "bg-accent text-accent-ink" : "bg-surface-2 text-muted")}>
                        <s.icon size={18} weight={on ? "fill" : "regular"} />
                      </span>
                      <span className="min-w-0">
                        <span className="block text-[17px] font-semibold tracking-tight">{s.title}</span>
                        <span className={cn("grid transition-[grid-template-rows] duration-500", on ? "grid-rows-[1fr]" : "grid-rows-[0fr]")}>
                          <span className="overflow-hidden">
                            <span className="block pt-1.5 text-[15px] leading-relaxed text-muted">{s.body}</span>
                          </span>
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </div>

          <div className="relative hidden aspect-[5/4] lg:block">
            <AnimatePresence mode="wait">
              <motion.div
                key={active}
                initial={reduce ? false : { opacity: 0, y: 18, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={reduce ? undefined : { opacity: 0, y: -12, scale: 0.98 }}
                transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                className="absolute inset-0 grid place-items-center"
              >
                <Visual i={active} />
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </div>
    </div>
  );
}

/* Sample data below: these are the real card styles the app uses, filled with example content. */
function Visual({ i }: { i: number }) {
  const shell = "w-full max-w-md rounded-card border border-line bg-surface p-6 shadow-card";
  if (i === 0)
    return (
      <div className={cn(shell, "stub [--notch-y:70%]")}>
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm text-muted">Member</p>
            <p className="mt-1 text-2xl font-semibold tracking-tight">Maya Fernandes</p>
          </div>
          <span className="rounded-full bg-ok-soft px-2.5 py-1 text-xs font-medium text-ok">Active</span>
        </div>
        <p className="num mt-8 text-3xl font-semibold tracking-wider">CL-7K2Q9M4D</p>
        <div className="perforation mt-6 h-[2px]" />
        <p className="mt-5 text-sm text-muted">Valid until 31 Jul 2027. Ticket prices 20% off, merch 10% off.</p>
      </div>
    );
  if (i === 1)
    return (
      <div className={shell}>
        <p className="text-lg font-semibold">Spring Gala</p>
        <div className="mt-5 space-y-3">
          {[["Member", "₹650", 78], ["Public", "₹950", 41]].map(([l, p, w]) => (
            <div key={l as string}>
              <div className="mb-1.5 flex justify-between text-sm"><span>{l}</span><span className="num">{p}</span></div>
              <div className="h-2 rounded-full bg-surface-2"><div className="h-2 rounded-full bg-accent" style={{ width: `${w}%` }} /></div>
            </div>
          ))}
        </div>
        <div className="mt-6 flex items-center gap-3 rounded-ctl bg-ok-soft p-3.5 text-ok">
          <CheckCircle size={22} weight="fill" />
          <div className="text-sm"><p className="font-semibold">Checked in</p><p className="opacity-80">Seat 2 of 3. Door scan took 0.8 s.</p></div>
        </div>
      </div>
    );
  if (i === 2)
    return (
      <div className={shell}>
        <p className="text-sm text-muted">To 412 subscribers</p>
        <p className="mt-2 text-xl font-semibold tracking-tight">General body meeting, Thursday 6 pm</p>
        <p className="mt-3 text-[15px] leading-relaxed text-muted">We are voting on the semester budget and the Open Mic format. Pizza after. Everyone is welcome.</p>
        <div className="mt-5 flex gap-2 text-xs"><span className="rounded-full bg-ok-soft px-2.5 py-1 text-ok">Website</span><span className="rounded-full bg-info-soft px-2.5 py-1 text-info">Mailing list</span></div>
      </div>
    );
  if (i === 3)
    return (
      <div className={shell}>
        <p className="text-lg font-semibold">Skyline Hoodie</p>
        <div className="mt-5 grid grid-cols-4 gap-2">
          {[["S", 12], ["M", 18], ["L", 14], ["XL", 0]].map(([s, n]) => (
            <div key={s as string} className={cn("rounded-ctl border p-3 text-center", n === 0 ? "border-line text-muted line-through" : "border-accent")}>
              <p className="font-semibold">{s}</p>
              <p className="num mt-1 text-xs text-muted">{n === 0 ? "gone" : `${n} left`}</p>
            </div>
          ))}
        </div>
        <p className="mt-5 text-sm text-muted">2 x M reserved for 15 minutes. Pay to keep them.</p>
      </div>
    );
  if (i === 4)
    return (
      <div className={shell}>
        <p className="text-lg font-semibold">Monsoon Bake Sale</p>
        <ul className="mt-4 divide-y divide-line">
          {[["Buy ingredients", "Aanya", "Done", "ok"], ["Bake 60 brownies", "Kabir", "In progress", "info"], ["Table and cash box", "Meera", "To do", "neutral"]].map(([t, o, s, tone]) => (
            <li key={t} className="flex items-center justify-between gap-3 py-3 text-sm">
              <span><span className="block font-medium">{t}</span><span className="text-muted">{o}</span></span>
              <span className={cn("rounded-full px-2.5 py-1 text-xs font-medium", tone === "ok" ? "bg-ok-soft text-ok" : tone === "info" ? "bg-info-soft text-info" : "bg-surface-2 text-muted")}>{s}</span>
            </li>
          ))}
        </ul>
      </div>
    );
  return (
    <div className={shell}>
      <p className="text-sm text-muted">Cash on hand</p>
      <p className="num mt-1 text-4xl font-semibold">{"₹"}4,90,000</p>
      <div className="mt-6 space-y-2.5 text-sm">
        {[["Dues", "₹45,000"], ["Tickets", "₹1,82,000"], ["Merchandise", "₹3,24,000"], ["Reimbursements paid", "-₹5,430"]].map(([k, v]) => (
          <div key={k} className="flex justify-between border-b border-line pb-2.5 last:border-0"><span className="text-muted">{k}</span><span className="num">{v}</span></div>
        ))}
      </div>
      <p className="mt-5 rounded-ctl bg-surface-2 p-3 text-xs text-muted">Term closed. Snapshot sealed with a checksum.</p>
    </div>
  );
}
