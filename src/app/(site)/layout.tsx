import { SiteNav } from "@/components/site-nav";
import { SiteFooter } from "@/components/site-footer";
import { maintain } from "@/lib/maintain";

export const dynamic = "force-dynamic";

export default async function SiteLayout({ children }: { children: React.ReactNode }) {
  await maintain();
  return (
    <>
      <SiteNav />
      <main id="content">{children}</main>
      <SiteFooter />
    </>
  );
}
