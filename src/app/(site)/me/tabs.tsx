"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";

const tabs = [
  { href: "/me", label: "Overview" },
  { href: "/me/tickets", label: "Tickets" },
  { href: "/me/orders", label: "Orders" },
  { href: "/me/card", label: "Member card" },
  { href: "/me/expenses", label: "Expenses" },
];

export function MeTabs() {
  const path = usePathname();
  return (
    <nav aria-label="My club" className="scrollbar-none -mx-4 flex gap-1 overflow-x-auto border-b border-line px-4 sm:mx-0 sm:px-0">
      {tabs.map((t) => {
        const on = t.href === "/me" ? path === "/me" : path.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            aria-current={on ? "page" : undefined}
            className={cn("relative whitespace-nowrap px-4 py-3 text-[15px] transition-colors", on ? "font-medium text-ink" : "text-muted hover:text-ink")}
          >
            {t.label}
            {on ? <span className="absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-accent" /> : null}
          </Link>
        );
      })}
    </nav>
  );
}
