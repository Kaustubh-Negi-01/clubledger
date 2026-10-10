"use client";

import { useEffect, useState } from "react";
import { Timer } from "@phosphor-icons/react";
import { cn } from "@/lib/cn";

export function Countdown({ until }: { until: string }) {
  const [left, setLeft] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setLeft(Math.max(0, Math.floor((new Date(until).getTime() - Date.now()) / 1000)));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [until]);
  if (left === null) return <div className="skeleton h-12" />;
  const mm = String(Math.floor(left / 60)).padStart(2, "0");
  const ss = String(left % 60).padStart(2, "0");
  return (
    <div className={cn("flex items-center gap-3 rounded-ctl p-3.5 text-sm", left === 0 ? "bg-warn-soft text-warn" : left < 120 ? "bg-warn-soft text-warn" : "bg-surface-2 text-muted")} role="timer" aria-live="off">
      <Timer size={20} />
      {left === 0 ? (
        <span>Your hold has expired. Paying now is recorded, but the treasurer will need to confirm your order.</span>
      ) : (
        <span>
          Held for you for <span className="num font-semibold text-ink">{mm}:{ss}</span>
        </span>
      )}
    </div>
  );
}
