import Link from "next/link";
import { List, SignOut, User, SquaresFour } from "@phosphor-icons/react/dist/ssr";
import { Brand } from "./brand";
import { Button } from "./ui/button";
import { ThemeToggle } from "./ui/theme-toggle";
import { getMe, isStaff } from "@/lib/session";
import { signOut } from "@/app/actions/auth";

const links = [
  { href: "/events", label: "Events" },
  { href: "/store", label: "Store" },
  { href: "/announcements", label: "News" },
  { href: "/fundraisers", label: "Fundraisers" },
];

export async function SiteNav() {
  const me = await getMe();
  const member = me?.membership?.status === "ACTIVE";
  return (
    <header className="sticky top-0 z-40 border-b border-line/70 bg-bg/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-6 px-4 sm:px-6">
        <Brand />
        <nav aria-label="Main" className="ml-4 hidden items-center gap-1 md:flex">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="rounded-ctl px-3 py-2 text-[15px] text-muted transition-colors hover:bg-surface-2 hover:text-ink">
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-1.5">
          <ThemeToggle />
          {me ? (
            <>
              {!member ? (
                <Button href="/join" size="sm" className="hidden sm:inline-flex">
                  Become a member
                </Button>
              ) : null}
              <details className="group relative">
                <summary className="flex size-10 cursor-pointer list-none items-center justify-center rounded-full bg-surface-2 text-sm font-semibold marker:hidden [&::-webkit-details-marker]:hidden" aria-label="Account menu">
                  {me.name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase()}
                </summary>
                <div className="absolute right-0 mt-2 w-64 rounded-card border border-line bg-surface p-2 shadow-card">
                  <div className="px-3 py-2.5">
                    <p className="truncate font-medium">{me.name}</p>
                    <p className="truncate text-sm text-muted">{me.email}</p>
                  </div>
                  <div className="my-1 h-px bg-line" />
                  <Link href="/me" className="flex items-center gap-2.5 rounded-ctl px-3 py-2.5 text-sm hover:bg-surface-2"><User size={18} /> My club</Link>
                  {isStaff(me) ? (
                    <Link href="/admin" className="flex items-center gap-2.5 rounded-ctl px-3 py-2.5 text-sm hover:bg-surface-2"><SquaresFour size={18} /> Officer console</Link>
                  ) : null}
                  <form action={signOut}>
                    <button className="flex w-full items-center gap-2.5 rounded-ctl px-3 py-2.5 text-sm text-muted hover:bg-surface-2 hover:text-ink"><SignOut size={18} /> Sign out</button>
                  </form>
                </div>
              </details>
            </>
          ) : (
            <>
              <Button href="/login" variant="ghost" size="sm" className="hidden sm:inline-flex">Sign in</Button>
              <Button href="/join" size="sm">Join the club</Button>
            </>
          )}
          <details className="relative md:hidden">
            <summary className="grid size-10 cursor-pointer list-none place-items-center rounded-full text-muted marker:hidden hover:bg-surface-2 [&::-webkit-details-marker]:hidden" aria-label="Menu">
              <List size={22} />
            </summary>
            <div className="absolute right-0 mt-2 w-56 rounded-card border border-line bg-surface p-2 shadow-card">
              {links.map((l) => (
                <Link key={l.href} href={l.href} className="block rounded-ctl px-3 py-2.5 text-sm hover:bg-surface-2">{l.label}</Link>
              ))}
              {!me ? <Link href="/login" className="block rounded-ctl px-3 py-2.5 text-sm hover:bg-surface-2">Sign in</Link> : null}
            </div>
          </details>
        </div>
      </div>
    </header>
  );
}
