import type { Metadata } from "next";
import { requireRole } from "@/lib/session";
import { rpc } from "@/lib/db";
import { dateTime } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardHeader } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";
import { AnnouncementForm } from "./form";

export const metadata: Metadata = { title: "Announcements" };

interface Row { id: number; title: string; body: string; status: string; published_at: string | null; created_at: string; queued: number }

export default async function AnnouncementsAdmin() {
  await requireRole("/admin/announcements", "comms");
  const rows = await rpc<Row[]>("api_announcements_admin");
  return (
    <>
      <PageHeader title="Announcements" description="Publishing posts to the website and queues one email per subscriber. Published posts are a permanent record and cannot be edited." />
      <div className="grid gap-8 lg:grid-cols-[1fr_26rem]">
        <div className="space-y-4">
          {rows.map((a) => (
            <Card key={a.id} className="p-5">
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-lg font-semibold tracking-tight">{a.title}</h2>
                <StatusBadge status={a.status} />
              </div>
              <p className="mt-2 line-clamp-3 whitespace-pre-line leading-relaxed text-muted">{a.body}</p>
              <p className="mt-3 text-sm text-muted">{a.published_at ? `Published ${dateTime(a.published_at)}, ${a.queued} email(s) queued` : `Draft from ${dateTime(a.created_at)}`}</p>
              {a.status === "DRAFT" ? <div className="mt-4 border-t border-line pt-4"><AnnouncementForm announcement={a} /></div> : null}
            </Card>
          ))}
        </div>
        <Card className="h-fit lg:sticky lg:top-8">
          <CardHeader title="Write an announcement" />
          <div className="p-5"><AnnouncementForm /></div>
        </Card>
      </div>
    </>
  );
}
