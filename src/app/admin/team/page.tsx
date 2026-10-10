import type { Metadata } from "next";
import { requireRole } from "@/lib/session";
import { rpc } from "@/lib/db";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardHeader } from "@/components/ui/card";
import { ActionButton } from "@/components/ui/action-form";
import { setRoleAction } from "@/app/actions/staff";
import { cn } from "@/lib/cn";
import { HandoverForm } from "./handover";

export const metadata: Metadata = { title: "Team" };

interface Row { id: string; full_name: string; email: string; roles: string[] }
const roles = [
  ["admin", "Admin", "Everything"],
  ["treasurer", "Treasurer", "Payments, expenses, finance, close"],
  ["organizer", "Organizer", "Events and check-in"],
  ["door", "Door", "Check-in and verification"],
  ["store", "Store", "Products, stock, orders"],
  ["comms", "Comms", "Announcements, mail, fundraisers"],
] as const;

export default async function TeamPage() {
  const me = await requireRole("/admin/team", "admin");
  const people = await rpc<Row[]>("api_members_admin");
  return (
    <>
      <PageHeader title="Team and handover" description="Roles take effect on the very next click. Nothing is cached, so removing a role removes access immediately." />
      <div className="space-y-3">
        {people.map((p) => (
          <Card key={p.id} className="p-5">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div><p className="font-medium">{p.full_name} {p.id === me.id ? <span className="text-sm text-muted">(you)</span> : null}</p><p className="text-sm text-muted">{p.email}</p></div>
              <div className="flex flex-wrap gap-1.5">
                {roles.map(([r, label]) => {
                  const on = p.roles.includes(r);
                  return (
                    <ActionButton key={r} action={setRoleAction.bind(null, p.id, r, !on)} variant={on ? "primary" : "ghost"} className={cn(!on && "opacity-80")}>
                      {on ? label : `+ ${label}`}
                    </ActionButton>
                  );
                })}
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Card className="mt-10">
        <CardHeader title="Officer handover" />
        <div className="p-5">
          <p className="mb-5 max-w-2xl text-sm leading-relaxed text-muted">After a term is closed, hand your roles to the incoming officer. The move is recorded with who, what and when, and is available once per closed term.</p>
          <HandoverForm people={people.filter((p) => p.id !== me.id).map((p) => ({ id: p.id, name: p.full_name }))} mine={roles.filter(([r]) => me.roles.includes(r as never)).map(([r, l]) => ({ role: r, label: l }))} />
        </div>
      </Card>
    </>
  );
}
