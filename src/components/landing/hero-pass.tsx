"use client";

import { Media } from "@/components/media";
import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from "motion/react";
import { useRef } from "react";

export interface PassProps {
  title: string;
  when: string;
  where: string;
  member: string;
  pub: string;
  code: string;
  image: string | null;
  qr: React.ReactNode;
}

/** The ticket pass: tilts toward the pointer and catches a moving sheen. Motion values keep it off React state. */
export function HeroPass({ title, when, where, member, pub, code, image, qr }: PassProps) {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  const px = useMotionValue(0.5);
  const py = useMotionValue(0.5);
  const sx = useSpring(px, { stiffness: 120, damping: 18 });
  const sy = useSpring(py, { stiffness: 120, damping: 18 });
  const rotateY = useTransform(sx, [0, 1], [-9, 9]);
  const rotateX = useTransform(sy, [0, 1], [7, -7]);
  const sheen = useTransform(sx, [0, 1], ["-30%", "130%"]);

  function onMove(e: React.PointerEvent) {
    if (reduce || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    px.set((e.clientX - r.left) / r.width);
    py.set((e.clientY - r.top) / r.height);
  }
  function onLeave() {
    px.set(0.5);
    py.set(0.5);
  }

  return (
    <div className="relative mx-auto w-full max-w-[24rem] [perspective:1200px]" onPointerMove={onMove} onPointerLeave={onLeave} ref={ref}>
      <motion.div
        initial={reduce ? false : { opacity: 0, y: 40, rotate: 3 }}
        animate={{ opacity: 1, y: 0, rotate: 0 }}
        transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1], delay: 0.15 }}
        style={reduce ? undefined : { rotateX, rotateY, transformStyle: "preserve-3d" }}
        className="stub relative overflow-hidden rounded-[22px] bg-surface shadow-card [--notch-y:61%] [--notch:13px]"
      >
        <div className="relative h-52">
          <Media src={image} quiet title={title} priority sizes="(min-width: 1024px) 24rem, 90vw" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/10 to-transparent" />
          <div className="absolute inset-x-5 bottom-4 text-white">
            <p className="text-2xl font-semibold tracking-tight">{title}</p>
            <p className="mt-1 text-sm text-white/85">{when}</p>
          </div>
        </div>
        <div className="space-y-4 px-5 pb-0 pt-5">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="text-muted">{where}</span>
            <span className="rounded-full bg-accent-soft px-2.5 py-1 text-xs font-medium text-accent">Member price</span>
          </div>
          <div className="flex items-baseline gap-3">
            <span className="num text-3xl font-semibold">{member}</span>
            <span className="num text-base text-muted line-through decoration-1">{pub}</span>
          </div>
        </div>
        <div className="perforation mx-5 mt-5 h-[2px]" aria-hidden />
        <div className="flex items-center gap-5 px-5 pb-5 pt-5">
          <div className="size-24 shrink-0 rounded-xl border border-line bg-white p-2 text-black [&_svg]:size-full">{qr}</div>
          <div className="min-w-0">
            <p className="text-xs text-muted">Admit one</p>
            <p className="num mt-1 truncate text-lg font-semibold tracking-wider">{code}</p>
            <p className="mt-2 text-xs leading-relaxed text-muted">Scanned at the door in a second. No printed list.</p>
          </div>
        </div>
        {!reduce ? (
          <motion.div
            aria-hidden
            className="pointer-events-none absolute inset-y-0 w-1/3 -skew-x-12 bg-gradient-to-r from-transparent via-white/25 to-transparent mix-blend-soft-light"
            style={{ left: sheen }}
          />
        ) : null}
      </motion.div>
    </div>
  );
}
