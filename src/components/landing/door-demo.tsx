"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import { CheckCircle, QrCode, WarningCircle } from "@phosphor-icons/react";
import { cn } from "@/lib/cn";

/** A tiny, honest sample of the door screen: first scan admits, second scan is refused. */
export function DoorDemo() {
  const [scans, setScans] = useState(0);
  const reduce = useReducedMotion();
  const state = scans === 0 ? "idle" : scans === 1 ? "ok" : "dup";
  return (
    <div className="flex h-full flex-col justify-between gap-6">
      <div>
        <h3 className="text-2xl font-semibold tracking-tight">The door needs a phone, not a list.</h3>
        <p className="mt-2 max-w-sm text-[15px] leading-relaxed text-white/70">Try it. Scan the same sample ticket twice.</p>
      </div>
      <div className="min-h-24" aria-live="polite">
        <AnimatePresence mode="wait">
          <motion.div
            key={state}
            initial={reduce ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0, y: -10 }}
            transition={{ duration: 0.25 }}
            className={cn(
              "flex items-center gap-3 rounded-ctl p-4",
              state === "ok" ? "bg-emerald-400/15 text-emerald-300" : state === "dup" ? "bg-amber-400/15 text-amber-300" : "bg-white/8 text-white/75",
            )}
          >
            {state === "ok" ? <CheckCircle size={30} weight="fill" /> : state === "dup" ? <WarningCircle size={30} weight="fill" /> : <QrCode size={30} />}
            <div>
              <p className="font-semibold">{state === "ok" ? "Checked in: Maya Fernandes" : state === "dup" ? "Already used" : "Ready to scan"}</p>
              <p className="num text-sm opacity-80">{state === "idle" ? "Sample ticket 7K2Q9M4D" : state === "ok" ? "Member ticket, seat 2" : "First scan was a moment ago"}</p>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>
      <div className="flex gap-2">
        <button onClick={() => setScans((s) => s + 1)} className="h-11 rounded-ctl bg-white px-5 text-[15px] font-medium text-black transition-transform active:scale-[0.97]">
          Scan sample ticket
        </button>
        {scans > 0 ? (
          <button onClick={() => setScans(0)} className="h-11 rounded-ctl px-4 text-[15px] text-white/70 hover:text-white">
            Reset
          </button>
        ) : null}
      </div>
    </div>
  );
}
