import Link from "next/link";
import { Brand } from "./brand";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-line">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-14 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div className="space-y-4">
          <Brand />
          <p className="max-w-xs text-sm leading-relaxed text-muted">
            Skyline Student Association runs events, memberships and merchandise on one platform, with books anyone on the team can read.
          </p>
        </div>
        <FooterCol title="Club" links={[["Events", "/events"], ["Store", "/store"], ["News", "/announcements"], ["Fundraisers", "/fundraisers"]]} />
        <FooterCol title="Members" links={[["Join the club", "/join"], ["Sign in", "/login"], ["My tickets", "/me/tickets"], ["My orders", "/me/orders"]]} />
        <FooterCol title="Officers" links={[["Officer console", "/admin"], ["Check-in", "/admin/checkin"], ["Finance", "/admin/finance"], ["Team", "/admin/team"]]} />
      </div>
      <div className="border-t border-line">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-5 text-sm text-muted sm:px-6">
          <span>Skyline Student Association</span>
          <span>Payments in this build are simulated. No real money moves.</span>
        </div>
      </div>
    </footer>
  );
}

function FooterCol({ title, links }: { title: string; links: [string, string][] }) {
  return (
    <div>
      <h3 className="mb-4 text-sm font-semibold">{title}</h3>
      <ul className="space-y-2.5">
        {links.map(([label, href]) => (
          <li key={href}>
            <Link href={href} className="text-sm text-muted transition-colors hover:text-ink">{label}</Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
