import { requireMe } from "@/lib/session";
import { MeTabs } from "./tabs";

export default async function MeLayout({ children }: { children: React.ReactNode }) {
  await requireMe("/me");
  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
      <MeTabs />
      <div className="mt-8">{children}</div>
    </div>
  );
}
