import { cn } from "@/lib/cn";

const control =
  "w-full rounded-ctl border border-line bg-surface px-3.5 text-[15px] text-ink placeholder:text-muted/80 transition-colors focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25 disabled:opacity-60";

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={cn("flex flex-col gap-2", className)}>
      <span className="text-sm font-medium">{label}</span>
      {children}
      {hint ? <span className="text-xs text-muted">{hint}</span> : null}
    </label>
  );
}

export function Input({ className, ...p }: React.ComponentProps<"input">) {
  return <input className={cn(control, "h-11", className)} {...p} />;
}

export function Textarea({ className, ...p }: React.ComponentProps<"textarea">) {
  return <textarea className={cn(control, "min-h-28 py-3 leading-relaxed", className)} {...p} />;
}

export function Select({ className, children, ...p }: React.ComponentProps<"select">) {
  return (
    <select className={cn(control, "h-11", className)} {...p}>
      {children}
    </select>
  );
}
