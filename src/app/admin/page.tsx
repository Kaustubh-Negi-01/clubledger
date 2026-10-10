import type { Metadata } from "next";
import Link from "next/link";
import { requireMe, hasRole } from "@/lib/session";
import { rpc } from "@/lib/db";
import { dateTime, inr } from "@/lib/format";
import { Card, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { Badge } from "@/components/ui/badge";
import { ActionButton } from "@/components/ui/action-form";
import { processMaintenanceAction } from "@/app/actions/staff";
import { cn } from "@/lib/cn";

export const metadata: Metadata = { title: "Officer console" };

interface Overview {
  term: string; active_members: number; tickets_sold: number; checked_in: number; low_stock: number; orders_to_hand_over: number;
  queued_mail: number; open_tasks: number; expenses_waiting: number | null; unfulfilled: number | null; income: number | null; spent: number | null; cash: number | null;
  upcoming: { id: number; title: string; starts_at: string; sold: number; capacity: number }[];
}

function Stat({ label, value, href, tone }: { label: string; value: React.ReactNode; href?: string; tone?: "warn" | "bad" }) {
  const body = (
    <Card className={cn("h-full p-5 transition-colors", href && "hover:bg-surface-2", tone === "warn" && "border-warn/40", tone === "bad" && "border-bad/40")}>
      <p className="text-sm text-muted">{label}</p>
      <p className="num display mt-2 text-4xl">{value}</p>
    </Card>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

export default async function AdminHome() {
  const me = await requireMe("/admin");
  const o = await rpc<Overview>("api_admin_overview");
  const fin = hasRole(me, "treasurer");
  return (
    <>
      <PageHeader title={`Good to see you, ${me.name.split(" ")[0]}.`} description={`Running ${o.term}. Here is what needs attention.`} actions={<ActionButton action={processMaintenanceAction} variant="secondary" size="sm">Run housekeeping</ActionButton>} />

      {fin && (o.unfulfilled || o.expenses_waiting) ? (
        <div className="mb-6 flex flex-wrap gap-3">
          {o.unfulfilled ? <Link href="/admin/payments?problem=1"><Badge tone="bad" className="px-3.5 py-2 text-sm">{o.unfulfilled} payment(s) received but not fulfilled</Badge></Link> : null}
          {o.expenses_waiting ? <Link href="/admin/expenses"><Badge tone="warn" className="px-3.5 py-2 text-sm">{o.expenses_waiting} expense(s) awaiting review</Badge></Link> : null}
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Active members" value={o.active_members} href="/admin/members" />
        <Stat label="Tickets sold" value={o.tickets_sold} href="/admin/events" />
        <Stat label="Checked in" value={o.checked_in} href="/admin/checkin" />
        <Stat label="Orders to hand over" value={o.orders_to_hand_over} href="/admin/orders" tone={o.orders_to_hand_over ? "warn" : undefined} />
        {fin ? (
          <>
            <Stat label="Cash in the bank" value={inr(o.cash)} href="/admin/finance" />
            <Stat label="Income this term" value={inr(o.income)} href="/admin/finance" />
            <Stat label="Spent this term" value={inr(o.spent)} href="/admin/finance" />
            <Stat label="Expenses waiting" value={o.expenses_waiting} href="/admin/expenses" tone={o.expenses_waiting ? "warn" : undefined} />
          </>
        ) : (
          <>
            <Stat label="Low stock sizes" value={o.low_stock} href="/admin/store" tone={o.low_stock ? "warn" : undefined} />
            <Stat label="Emails queued" value={o.queued_mail} href="/admin/mail" />
            <Stat label="Open fundraiser tasks" value={o.open_tasks} href="/fundraisers" />
          </>
        )}
      </div>

      <Card className="mt-8">
        <CardHeader title="Next events" action={<Link href="/admin/events" className="text-sm font-medium text-accent">Manage events</Link>} />
        <ul className="divide-y divide-line px-5 pb-2 pt-2">
          {o.upcoming.map((e) => {
            const pct = Math.round((e.sold / e.capacity) * 100);
            return (
              <li key={e.id} className="grid items-center gap-3 py-4 sm:grid-cols-[1fr_14rem]">
                <div>
                  <Link href={`/admin/events/${e.id}`} className="font-medium hover:text-accent">{e.title}</Link>
                  <p className="text-sm text-muted">{dateTime(e.starts_at)}</p>
                </div>
                <div>
                  <div className="mb-1.5 flex justify-between text-xs text-muted"><span>{e.sold} sold</span><span className="num">{pct}% of {e.capacity}</span></div>
                  <div className="h-2 overflow-hidden rounded-full bg-surface-2"><div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} /></div>
                </div>
              </li>
            );
          })}
          {o.upcoming.length === 0 ? <li className="py-6 text-sm text-muted">No events on sale.</li> : null}
        </ul>
      </Card>
    </>
  );
}
