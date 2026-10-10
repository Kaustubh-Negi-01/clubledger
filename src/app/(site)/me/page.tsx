import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, CalendarCheck, IdentificationCard, ShoppingBagOpen, WarningCircle } from "@phosphor-icons/react/dist/ssr";
import { rpc } from "@/lib/db";
import { requireMe } from "@/lib/session";
import { validThrough, inr, relative } from "@/lib/format";
import type { Task } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import { ActionButton } from "@/components/ui/action-form";
import { setTaskStatusAction } from "@/app/actions/member";

export const metadata: Metadata = { title: "My club" };

interface Home {
  open_payments: { id: string; purpose: string; amount_paise: number; created_at: string }[];
  upcoming_tickets: number;
  orders_open: number;
  tasks_open: number;
}
type MyTask = Task & { fundraiser: string; fundraiser_id: number };

export default async function MePage({ searchParams }: { searchParams: Promise<{ denied?: string }> }) {
  const { denied } = await searchParams;
  const me = await requireMe("/me");
  const [home, tasks] = await Promise.all([rpc<Home>("api_member_home"), rpc<MyTask[]>("api_my_tasks")]);
  const m = me.membership;
  const active = m?.status === "ACTIVE";
  const first = me.name.split(" ")[0];

  return (
    <div className="space-y-8">
      {denied ? (
        <p role="alert" className="flex items-center gap-2 rounded-ctl bg-warn-soft px-4 py-3 text-sm text-warn"><WarningCircle size={18} weight="fill" /> That page is for officers. Ask the president for access if you need it.</p>
      ) : null}
      <div>
        <h1 className="display text-4xl md:text-5xl">Hi {first}.</h1>
        <p className="mt-3 text-lg text-muted">{active ? "Your membership is active. Member prices apply everywhere." : "You are signed up. Join to unlock member prices."}</p>
      </div>

      {home.open_payments.length ? (
        <Card className="border-warn/40 bg-warn-soft/60">
          <div className="flex flex-wrap items-center justify-between gap-4 p-5">
            <div>
              <p className="font-semibold">You have {home.open_payments.length} unfinished checkout{home.open_payments.length > 1 ? "s" : ""}</p>
              <p className="mt-1 text-sm text-muted">Holds and reservations expire quickly, so finish them while they are still yours.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {home.open_payments.map((p) => (
                <Button key={p.id} href={`/pay/${p.id}`} size="sm">Pay {inr(p.amount_paise)} ({p.purpose.toLowerCase()})</Button>
              ))}
            </div>
          </div>
        </Card>
      ) : null}

      <div className="grid gap-5 md:grid-cols-3">
        <Card className="p-6 md:col-span-2">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="flex items-center gap-2 text-sm text-muted"><IdentificationCard size={18} /> Membership</p>
              <p className="mt-2 text-2xl font-semibold tracking-tight">{m ? m.plan_name : "Not a member yet"}</p>
            </div>
            {m ? <StatusBadge status={m.status} /> : null}
          </div>
          {m && active ? (
            <>
              <dl className="mt-6 grid gap-4 text-sm sm:grid-cols-3">
                <div><dt className="text-muted">Member code</dt><dd className="num mt-1 text-lg font-semibold">{m.member_code}</dd></div>
                <div><dt className="text-muted">Valid through</dt><dd className="mt-1 text-lg font-semibold">{validThrough(m.expires_at)}</dd></div>
                <div><dt className="text-muted">Ticket discount</dt><dd className="num mt-1 text-lg font-semibold">{m.ticket_discount_bps / 100}%</dd></div>
              </dl>
              <Button href="/me/card" variant="secondary" size="sm" className="mt-6">Show member card <ArrowRight size={16} /></Button>
            </>
          ) : (
            <div className="mt-6 flex flex-wrap items-center gap-4">
              <p className="max-w-md text-[15px] leading-relaxed text-muted">Pay the annual dues once to get cheaper tickets, 10% off merchandise and a QR card for the door.</p>
              <Button href="/join">Join the club</Button>
            </div>
          )}
        </Card>

        <div className="grid gap-5">
          <Link href="/me/tickets"><Card className="h-full p-6 transition-colors hover:bg-surface-2"><p className="flex items-center gap-2 text-sm text-muted"><CalendarCheck size={18} /> Upcoming tickets</p><p className="num display mt-3 text-5xl">{home.upcoming_tickets}</p></Card></Link>
          <Link href="/me/orders"><Card className="h-full p-6 transition-colors hover:bg-surface-2"><p className="flex items-center gap-2 text-sm text-muted"><ShoppingBagOpen size={18} /> Open orders</p><p className="num display mt-3 text-5xl">{home.orders_open}</p></Card></Link>
        </div>
      </div>

      {tasks.length ? (
        <Card>
          <CardHeader title="Your fundraiser tasks" action={<Link href="/fundraisers" className="text-sm font-medium text-accent">All fundraisers</Link>} />
          <ul className="divide-y divide-line px-5 pb-2 pt-3">
            {tasks.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center justify-between gap-3 py-3.5">
                <div>
                  <p className="font-medium">{t.title}</p>
                  <p className="text-sm text-muted">{t.fundraiser}{t.due_on ? `, due ${relative(t.due_on)}` : ""}</p>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={t.status} />
                  {t.status !== "DONE" ? <ActionButton action={setTaskStatusAction.bind(null, t.id, "DONE")} variant="secondary">Mark done</ActionButton> : null}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}
