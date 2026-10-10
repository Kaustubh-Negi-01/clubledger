import { cn } from "@/lib/cn";

export function TableWrap({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("overflow-x-auto rounded-card border border-line bg-surface shadow-card", className)}>{children}</div>;
}
export function Table({ children, className }: { children: React.ReactNode; className?: string }) {
  return <table className={cn("w-full min-w-[40rem] border-collapse text-left text-[15px]", className)}>{children}</table>;
}
export function Th({ children, className, align }: { children?: React.ReactNode; className?: string; align?: "right" }) {
  return <th scope="col" className={cn("border-b border-line bg-surface-2/60 px-4 py-3 text-xs font-medium text-muted", align === "right" && "text-right", className)}>{children}</th>;
}
export function Td({ children, className, align, num }: { children?: React.ReactNode; className?: string; align?: "right"; num?: boolean }) {
  return <td className={cn("border-b border-line px-4 py-3.5 align-middle last:border-b-0", align === "right" && "text-right", num && "num", className)}>{children}</td>;
}
export function Tr({ children, className }: { children: React.ReactNode; className?: string }) {
  return <tr className={cn("[&:last-child>td]:border-b-0", className)}>{children}</tr>;
}
