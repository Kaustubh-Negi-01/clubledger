"use client";

import { animate, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

/** Counts to the live number once it scrolls into view. Static under reduced motion. */
export function CountUp({ value }: { value: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.6 });
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(reduce ? value : 0);
  useEffect(() => {
    if (!inView) return;
    if (reduce) {
      setShown(value);
      return;
    }
    const c = animate(0, value, { duration: 1.4, ease: [0.16, 1, 0.3, 1], onUpdate: (v) => setShown(Math.round(v)) });
    return () => c.stop();
  }, [inView, value, reduce]);
  return (
    <span ref={ref} className="num">
      {shown.toLocaleString("en-IN")}
    </span>
  );
}
