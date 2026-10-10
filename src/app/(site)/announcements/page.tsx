import type { Metadata } from "next";
import Link from "next/link";
import { Megaphone } from "@phosphor-icons/react/dist/ssr";
import { rpc } from "@/lib/db";
import { dateOnly } from "@/lib/format";
import type { Announcement } from "@/lib/types";
import { PageHeader } from "@/components/ui/page-header";
import { Empty } from "@/components/ui/empty";
import { SubscribeForm } from "@/components/subscribe-form";

export const metadata: Metadata = { title: "News" };

export default async function AnnouncementsPage() {
  const items = await rpc<Announcement[]>("api_announcements_list", { p_limit: 50 });
  return (
    <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
      <PageHeader title="News from the committee" description="Everything the club has announced, newest first. The same words go out by email." />
      <div className="grid gap-12 lg:grid-cols-[1fr_22rem]">
        <div>
          {items.length ? (
            <ol className="divide-y divide-line border-y border-line">
              {items.map((a) => (
                <li key={a.id}>
                  <Link href={`/announcements/${a.id}`} className="group grid gap-2 py-7 md:grid-cols-[9rem_1fr] md:gap-8">
                    <time dateTime={a.published_at} className="num text-sm text-muted">{dateOnly(a.published_at)}</time>
                    <div>
                      <h2 className="text-xl font-semibold tracking-tight group-hover:text-accent">{a.title}</h2>
                      <p className="mt-2 line-clamp-2 max-w-[65ch] leading-relaxed text-muted">{a.body}</p>
                    </div>
                  </Link>
                </li>
              ))}
            </ol>
          ) : (
            <Empty icon={Megaphone} title="No announcements yet">When the committee posts something, it lands here and in your inbox.</Empty>
          )}
        </div>
        <aside className="h-fit rounded-card border border-line bg-surface p-6 shadow-card lg:sticky lg:top-24">
          <h2 className="text-lg font-semibold tracking-tight">Get it by email</h2>
          <p className="mb-5 mt-2 text-sm leading-relaxed text-muted">One message per announcement. Unsubscribe from any email.</p>
          <SubscribeForm />
        </aside>
      </div>
    </div>
  );
}
