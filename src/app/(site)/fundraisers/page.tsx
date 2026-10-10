import type { Metadata } from "next";
import { CookingPot } from "@phosphor-icons/react/dist/ssr";
import { rpc } from "@/lib/db";
import { getMe, hasRole } from "@/lib/session";
import { dateOnly, inr } from "@/lib/format";
import type { Fundraiser } from "@/lib/types";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { Empty } from "@/components/ui/empty";
import { StatusBadge, Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ActionButton } from "@/components/ui/action-form";
import { setTaskStatusAction } from "@/app/actions/member";
import { FundraiserForms, TaskForm } from "./forms";

export const metadata: Metadata = { title: "Fundraisers" };

const columns = [
  ["TODO", "To do"],
  ["DOING", "In progress"],
  ["BLOCKED", "Blocked"],
  ["DONE", "Done"],
] as const;

export default async function FundraisersPage() {
  const me = await getMe();
  if (!me)
    return (
      <div className="mx-auto max-w-3xl px-4 py-20 text-center sm:px-6">
        <h1 className="display text-4xl md:text-5xl">Fundraisers are for members.</h1>
        <p className="mx-auto mt-4 max-w-md text-muted">Sign in to see what is being planned, who is doing what, and how it is going.</p>
        <Button href="/login?next=/fundraisers" className="mt-8">Sign in</Button>
      </div>
    );
  const [list, people] = await Promise.all([
    rpc<Fundraiser[]>("api_fundraisers"),
    hasRole(me, "comms") ? rpc<{ id: string; name: string }[]>("api_people") : Promise.resolve([]),
  ]);
  const manage = hasRole(me, "comms");

  return (
    <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
      <PageHeader title="Fundraisers" description="What needs doing, who owns it, and whether we are on track." actions={manage ? <FundraiserForms /> : undefined} />
      {list.length === 0 ? (
        <Empty icon={CookingPot} title="No fundraisers yet">Organizers can start one here and split the work into tasks.</Empty>
      ) : (
        <div className="space-y-10">
          {list.map((f) => {
            const pct = f.tasks_total ? Math.round((f.tasks_done / f.tasks_total) * 100) : 0;
            return (
              <section key={f.id} aria-labelledby={`f-${f.id}`}>
                <Card className="p-6 md:p-8">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="max-w-2xl">
                      <div className="flex items-center gap-3">
                        <h2 id={`f-${f.id}`} className="text-2xl font-semibold tracking-tight">{f.title}</h2>
                        <StatusBadge status={f.status} />
                      </div>
                      <p className="mt-2 leading-relaxed text-muted">{f.description}</p>
                    </div>
                    <div className="flex gap-8 text-right">
                      <div><p className="text-sm text-muted">Tasks done</p><p className="num text-3xl font-semibold">{f.tasks_done}/{f.tasks_total}</p></div>
                      {f.goal_paise ? <div><p className="text-sm text-muted">Goal</p><p className="num text-3xl font-semibold">{inr(f.goal_paise)}</p></div> : null}
                      <div><p className="text-sm text-muted">Spent</p><p className="num text-3xl font-semibold">{inr(f.spent_paise)}</p></div>
                    </div>
                  </div>
                  <div className="mt-6 flex items-center gap-4">
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`${f.title} progress`}>
                      <div className="h-full rounded-full bg-accent transition-[width] duration-700" style={{ width: `${pct}%` }} />
                    </div>
                    <span className="num w-12 text-right text-sm">{pct}%</span>
                    {f.tasks_overdue > 0 ? <Badge tone="bad">{f.tasks_overdue} overdue</Badge> : <Badge tone="ok">On track</Badge>}
                  </div>
                  <div className="mt-8 grid gap-4 md:grid-cols-4">
                    {columns.map(([st, label]) => {
                      const items = f.tasks.filter((t) => t.status === st);
                      return (
                        <div key={st} className="rounded-ctl bg-bg p-3">
                          <p className="mb-3 flex items-center justify-between px-1 text-sm font-medium">{label}<span className="num text-muted">{items.length}</span></p>
                          <ul className="space-y-2">
                            {items.map((t) => (
                              <li key={t.id} className="rounded-ctl border border-line bg-surface p-3.5 text-sm">
                                <p className="font-medium">{t.title}</p>
                                <p className="mt-1 text-muted">{t.owner ?? "Unassigned"}{t.due_on ? `, ${dateOnly(t.due_on)}` : ""}</p>
                                {(t.owner_id === me.id || manage) && st !== "DONE" ? (
                                  <div className="mt-2.5 flex gap-1.5">
                                    {st === "TODO" ? <ActionButton action={setTaskStatusAction.bind(null, t.id, "DOING")} variant="secondary">Start</ActionButton> : null}
                                    {st === "DOING" ? <ActionButton action={setTaskStatusAction.bind(null, t.id, "DONE")} variant="secondary">Done</ActionButton> : null}
                                    {st !== "BLOCKED" ? <ActionButton action={setTaskStatusAction.bind(null, t.id, "BLOCKED")} variant="ghost">Blocked</ActionButton> : <ActionButton action={setTaskStatusAction.bind(null, t.id, "DOING")} variant="secondary">Unblock</ActionButton>}
                                  </div>
                                ) : null}
                              </li>
                            ))}
                            {items.length === 0 ? <li className="px-1 py-3 text-xs text-muted">Nothing here</li> : null}
                          </ul>
                        </div>
                      );
                    })}
                  </div>
                  {manage ? <TaskForm fundraiserId={f.id} people={people} /> : null}
                </Card>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
