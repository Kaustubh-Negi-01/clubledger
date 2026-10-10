import type { Icon } from "@phosphor-icons/react";
import { cn } from "@/lib/cn";

export function Empty({ icon: IconC, title, children, className }: { icon: Icon; title: string; children?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 rounded-card border border-dashed border-line px-6 py-14 text-center", className)}>
      <span className="grid size-12 place-items-center rounded-full bg-surface-2 text-muted">
        <IconC size={22} weight="regular" />
      </span>
      <p className="font-medium">{title}</p>
      {children ? <div className="max-w-sm text-sm leading-relaxed text-muted">{children}</div> : null}
    </div>
  );
}
