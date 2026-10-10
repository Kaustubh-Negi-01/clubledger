import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "@phosphor-icons/react/dist/ssr";
import { rpc } from "@/lib/db";
import { dateOnly } from "@/lib/format";
import type { Announcement } from "@/lib/types";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const a = await rpc<Announcement | null>("api_announcement_get", { p_id: Number(id) }).catch(() => null);
  return { title: a?.title ?? "News" };
}

export default async function AnnouncementPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const a = Number.isFinite(Number(id)) ? await rpc<Announcement | null>("api_announcement_get", { p_id: Number(id) }) : null;
  if (!a) notFound();
  return (
    <article className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
      <Link href="/announcements" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink"><ArrowLeft size={16} /> All news</Link>
      <h1 className="display mt-6 text-4xl md:text-6xl">{a.title}</h1>
      <p className="mt-5 text-muted">
        <time dateTime={a.published_at}>{dateOnly(a.published_at)}</time> by {a.author}
      </p>
      <div className="mt-10 max-w-[65ch] whitespace-pre-line text-lg leading-relaxed">{a.body}</div>
    </article>
  );
}
