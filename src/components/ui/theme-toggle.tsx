"use client";

import { Moon, Sun } from "@phosphor-icons/react";
import { useSyncExternalStore } from "react";

function subscribe(cb: () => void) {
  const obs = new MutationObserver(cb);
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => obs.disconnect();
}

export function ThemeToggle() {
  const dark = useSyncExternalStore(
    subscribe,
    () => document.documentElement.classList.contains("dark"),
    () => false,
  );
  return (
    <button
      type="button"
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      onClick={() => {
        const next = !document.documentElement.classList.contains("dark");
        document.documentElement.classList.toggle("dark", next);
        try {
          localStorage.setItem("cl-theme", next ? "dark" : "light");
        } catch {}
      }}
      className="grid size-10 place-items-center rounded-full text-muted transition-colors hover:bg-surface-2 hover:text-ink"
    >
      {dark ? <Sun size={20} /> : <Moon size={20} />}
    </button>
  );
}
