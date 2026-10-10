import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowSquareOut } from "@phosphor-icons/react/dist/ssr";
import { requireMe, hasRole, isStaff } from "@/lib/session";
import { maintain } from "@/lib/maintain";
import { Brand } from "@/components/brand";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { AdminNav, type NavItem } from "./nav";
import type { Role } from "@/lib/types";

export const dynamic = "force-dynamic";

const items: (NavItem & { roles: Role[] })[] = [
  { href: "/admin", label: "Overview", icon: "overview", roles: ["organizer", "door", "store", "comms", "treasurer"], group: "Club" },
  { href: "/admin/checkin", label: "Door check-in", icon: "checkin", roles: ["door", "organizer"], group: "Club" },
  { href: "/admin/members", label: "Members", icon: "members", roles: ["door", "organizer", "treasurer"], group: "Club" },
  { href: "/admin/events", label: "Events", icon: "events", roles: ["organizer"], group: "Run" },
  { href: "/admin/store", label: "Products and stock", icon: "store", roles: ["store"], group: "Run" },
  { href: "/admin/orders", label: "Orders", icon: "orders", roles: ["store"], group: "Run" },
  { href: "/admin/announcements", label: "Announcements", icon: "news", roles: ["comms"], group: "Run" },
  { href: "/admin/mail", label: "Mail log", icon: "mail", roles: ["comms"], group: "Run" },
  { href: "/admin/payments", label: "Payments", icon: "payments", roles: ["treasurer"], group: "Money" },
  { href: "/admin/expenses", label: "Expenses", icon: "expenses", roles: ["treasurer"], group: "Money" },
  { href: "/admin/finance", label: "Finance", icon: "finance", roles: ["treasurer"], group: "Money" },
  { href: "/admin/close", label: "Close the term", icon: "close", roles: ["treasurer"], group: "Money" },
  { href: "/admin/team", label: "Team and handover", icon: "team", roles: ["admin"], group: "Admin" },
];

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const me = await requireMe("/admin");
  if (!isStaff(me)) redirect("/me?denied=1");
  await maintain();
  const nav = items.filter((i) => hasRole(me, ...i.roles)).map(({ roles: _r, ...rest }) => rest);

  return (
    <div className="min-h-[100dvh] lg:grid lg:grid-cols-[17rem_1fr]">
      <aside className="border-b border-line bg-surface lg:sticky lg:top-0 lg:h-[100dvh] lg:overflow-y-auto lg:border-b-0 lg:border-r">
        <div className="flex h-16 items-center justify-between px-5">
          <Brand href="/admin" />
        </div>
        <AdminNav items={nav} />
        <div className="hidden items-center justify-between gap-2 border-t border-line p-4 lg:flex">
          <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">Public site <ArrowSquareOut size={14} /></Link>
          <ThemeToggle />
        </div>
      </aside>
      <div className="min-w-0">
        <div className="mx-auto max-w-6xl px-4 py-8 sm:px-8 lg:py-10">{children}</div>
      </div>
    </div>
  );
}
