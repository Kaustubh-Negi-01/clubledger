"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bag, Broadcast, CalendarBlank, ChartLineUp, EnvelopeSimple, HandCoins, IdentificationCard, Lock, Package, QrCode, Receipt,
  SquaresFour, Users, UsersThree, type Icon,
} from "@phosphor-icons/react";
import { cn } from "@/lib/cn";

const icons: Record<string, Icon> = {
  overview: SquaresFour, checkin: QrCode, members: IdentificationCard, events: CalendarBlank, store: Package, orders: Bag,
  news: Broadcast, mail: EnvelopeSimple, payments: HandCoins, expenses: Receipt, finance: ChartLineUp, close: Lock, team: UsersThree,
};

export interface NavItem { href: string; label: string; icon: string; group: string }

export function AdminNav({ items }: { items: NavItem[] }) {
  const path = usePathname();
  const groups = [...new Set(items.map((i) => i.group))];
  return (
    <nav aria-label="Officer console" className="scrollbar-none flex gap-1 overflow-x-auto px-3 pb-3 lg:block lg:space-y-6 lg:overflow-visible lg:px-3 lg:pb-6">
      {groups.map((g) => (
        <div key={g} className="flex gap-1 lg:block">
          <p className="mb-2 mt-1 hidden px-3 text-xs font-medium text-muted lg:block">{g}</p>
          <ul className="flex gap-1 lg:block lg:space-y-0.5">
            {items.filter((i) => i.group === g).map((i) => {
              const I = icons[i.icon] ?? Users;
              const on = i.href === "/admin" ? path === "/admin" : path.startsWith(i.href);
              return (
                <li key={i.href}>
                  <Link
                    href={i.href}
                    aria-current={on ? "page" : undefined}
                    className={cn("flex items-center gap-2.5 whitespace-nowrap rounded-ctl px-3 py-2.5 text-[15px] transition-colors", on ? "bg-accent-soft font-medium text-accent" : "text-muted hover:bg-surface-2 hover:text-ink")}
                  >
                    <I size={19} weight={on ? "fill" : "regular"} />
                    {i.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
