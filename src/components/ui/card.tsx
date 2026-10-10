import { cn } from "@/lib/cn";

export function Card({ className, children, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("rounded-card border border-line bg-surface shadow-card", className)} {...p}>
      {children}
    </div>
  );
}

export function CardHeader({ title, action, className }: { title: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-center justify-between gap-3 px-5 pt-5", className)}>
      <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
      {action}
    </div>
  );
}
