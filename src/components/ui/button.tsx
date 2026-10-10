import Link from "next/link";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const base =
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-ctl font-medium transition-[transform,background-color,box-shadow,opacity,filter] duration-200 select-none active:translate-y-px active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50";
const variants: Record<Variant, string> = {
  primary:
    "bg-accent text-accent-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.25),0_8px_20px_-10px_var(--accent)] hover:brightness-110",
  secondary: "border border-line bg-surface text-ink hover:bg-surface-2",
  ghost: "text-ink hover:bg-surface-2",
  danger: "border border-transparent bg-bad-soft text-bad hover:brightness-95",
};
const sizes: Record<Size, string> = {
  sm: "h-9 px-3.5 text-sm",
  md: "h-11 px-5 text-[15px]",
  lg: "h-[52px] px-7 text-base",
};

export function buttonClass(variant: Variant = "primary", size: Size = "md", className?: string) {
  return cn(base, variants[variant], sizes[size], className);
}

type Props = { variant?: Variant; size?: Size; className?: string; children: React.ReactNode } & (
  | ({ href: string } & Omit<React.ComponentProps<typeof Link>, "href" | "className" | "children">)
  | ({ href?: undefined } & React.ButtonHTMLAttributes<HTMLButtonElement>)
);

export function Button({ variant = "primary", size = "md", className, children, ...rest }: Props) {
  const cls = buttonClass(variant, size, className);
  if ("href" in rest && rest.href !== undefined) {
    const { href, ...linkRest } = rest;
    return (
      <Link href={href} className={cls} {...linkRest}>
        {children}
      </Link>
    );
  }
  return (
    <button className={cls} {...(rest as React.ButtonHTMLAttributes<HTMLButtonElement>)}>
      {children}
    </button>
  );
}
