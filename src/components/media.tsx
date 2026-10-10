import Image from "next/image";
import { BaseballCap, Broom, Code, Confetti, Hoodie, Microphone, Ticket, Tote, Trophy, TShirt } from "@phosphor-icons/react/dist/ssr";
import type { Icon } from "@phosphor-icons/react";
import { cn } from "@/lib/cn";

function hash(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

const glyphs: [RegExp, Icon][] = [
  [/hoodie|sweat/i, Hoodie],
  [/shirt|tee/i, TShirt],
  [/tote|bag/i, Tote],
  [/cap|hat/i, BaseballCap],
  [/mic|music|band|concert/i, Microphone],
  [/gala|party|night out|celebrat/i, Confetti],
  [/clean|green|lake/i, Broom],
  [/hack|code|tech/i, Code],
  [/quiz|trophy|award|contest/i, Trophy],
];

/**
 * Generated poster art for items without a photo: layered gradients in the single accent colour,
 * positioned from a hash of the title so every item looks distinct but stable, with a large glyph that
 * hints at what it is. Offline and instant. Officers can add a real photo URL at any time.
 */
export function Poster({ title, className }: { title: string; className?: string; quiet?: boolean }) {
  const h = hash(title);
  const p = (n: number, lo: number, hi: number) => lo + (((h >>> n) & 0xffff) % (hi - lo));
  const Glyph = glyphs.find(([re]) => re.test(title))?.[1] ?? Ticket;
  return (
    <div
      aria-hidden
      className={cn("absolute inset-0 overflow-hidden", className)}
      style={{
        background: [
          `radial-gradient(${p(2, 55, 85)}% ${p(5, 60, 90)}% at ${p(8, 10, 90)}% ${p(11, 0, 60)}%, color-mix(in oklab, var(--accent) 78%, transparent), transparent 62%)`,
          `radial-gradient(${p(14, 40, 70)}% ${p(17, 50, 80)}% at ${p(20, 20, 100)}% ${p(23, 50, 110)}%, color-mix(in oklab, var(--ink) 22%, transparent), transparent 68%)`,
          `linear-gradient(${p(26, 120, 220)}deg, var(--surface-2), var(--bg))`,
        ].join(","),
      }}
    >
      <Glyph weight="duotone" className="absolute right-[8%] top-1/2 h-[46%] w-auto -translate-y-1/2 text-ink/80 drop-shadow-sm" />
    </div>
  );
}

/** A photo when there is one, generated poster art when there is not. The parent must be `relative` with a size. */
export function Media({
  src,
  title,
  sizes,
  priority,
  className,
  quiet,
}: {
  src?: string | null;
  title: string;
  sizes: string;
  priority?: boolean;
  className?: string;
  quiet?: boolean;
}) {
  if (!src) return <Poster title={title} className={className} quiet={quiet} />;
  return <Image src={src} alt="" fill sizes={sizes} priority={priority} className={cn("object-cover", className)} />;
}
