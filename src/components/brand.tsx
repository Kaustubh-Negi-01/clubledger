import Link from "next/link";
import { cn } from "@/lib/cn";

export function Brand({ className, href = "/" }: { className?: string; href?: string }) {
  return (
    <Link href={href} className={cn("group inline-flex items-center gap-2.5 font-semibold tracking-tight", className)} aria-label="Skyline Student Association home">
      <span
        aria-hidden
        className="stub relative grid size-8 place-items-center bg-accent text-accent-ink [--notch:5px] [--notch-y:50%]"
        style={{ borderRadius: 8 }}
      >
        <span className="num text-[13px] font-bold leading-none">S</span>
      </span>
      <span className="text-[17px] leading-none">
        Skyline<span className="hidden font-normal text-muted lg:inline"> Student Association</span>
      </span>
    </Link>
  );
}
