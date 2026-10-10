import { cn } from "@/lib/cn";

type Tone = "neutral" | "ok" | "warn" | "bad" | "info" | "accent";
const tones: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted",
  ok: "bg-ok-soft text-ok",
  warn: "bg-warn-soft text-warn",
  bad: "bg-bad-soft text-bad",
  info: "bg-info-soft text-info",
  accent: "bg-accent-soft text-accent",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: React.ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium leading-none", tones[tone], className)}>
      {children}
    </span>
  );
}

const map: Record<string, [Tone, string]> = {
  ACTIVE: ["ok", "Active"],
  PENDING: ["warn", "Pending"],
  EXPIRED: ["neutral", "Expired"],
  REVOKED: ["bad", "Revoked"],
  CANCELLED: ["neutral", "Cancelled"],
  ISSUED: ["ok", "Valid"],
  USED: ["info", "Checked in"],
  REFUNDED: ["neutral", "Refunded"],
  VOID: ["neutral", "Void"],
  CREATED: ["warn", "Awaiting payment"],
  SUCCEEDED: ["ok", "Paid"],
  FAILED: ["bad", "Failed"],
  RESERVED: ["warn", "Reserved"],
  PAID: ["ok", "Paid"],
  PICKED_UP: ["info", "Picked up"],
  SUBMITTED: ["warn", "Awaiting review"],
  APPROVED: ["info", "Approved"],
  REJECTED: ["bad", "Rejected"],
  DRAFT: ["neutral", "Draft"],
  ON_SALE: ["ok", "On sale"],
  CLOSED: ["neutral", "Closed"],
  PUBLISHED: ["ok", "Published"],
  TODO: ["neutral", "To do"],
  DOING: ["info", "In progress"],
  DONE: ["ok", "Done"],
  BLOCKED: ["bad", "Blocked"],
  QUEUED: ["warn", "Queued"],
  SENT: ["ok", "Delivered"],
  SUPPRESSED: ["neutral", "Suppressed"],
  UNFULFILLED: ["bad", "Needs resolving"],
  PLANNING: ["neutral", "Planning"],
};

export function StatusBadge({ status }: { status: string }) {
  const [tone, label] = map[status] ?? ["neutral", status];
  return <Badge tone={tone}>{label}</Badge>;
}
