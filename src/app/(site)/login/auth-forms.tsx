"use client";

import { useState } from "react";
import { GoogleLogo } from "@phosphor-icons/react";
import { ActionForm, SubmitButton } from "@/components/ui/action-form";
import { Field, Input } from "@/components/ui/field";
import { Button } from "@/components/ui/button";
import { supabaseBrowser } from "@/lib/supabase-browser";
import { magicLink, passwordAuth } from "@/app/actions/auth";
import { cn } from "@/lib/cn";

type Mode = "signin" | "signup" | "link";

export function AuthForms({ next }: { next: string }) {
  const [mode, setMode] = useState<Mode>("signin");
  const [busy, setBusy] = useState(false);

  async function google() {
    setBusy(true);
    const sb = supabaseBrowser();
    await sb.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}` },
    });
  }

  return (
    <div className="mt-6 space-y-6">
      <Button variant="secondary" size="lg" className="w-full" onClick={google} disabled={busy}>
        <GoogleLogo size={20} weight="bold" /> Continue with Google
      </Button>
      <div className="flex items-center gap-3 text-xs text-muted">
        <span className="h-px flex-1 bg-line" /> or use your email <span className="h-px flex-1 bg-line" />
      </div>

      <div role="tablist" aria-label="Email sign-in method" className="grid grid-cols-3 gap-1 rounded-ctl bg-surface-2 p-1 text-sm">
        {([["signin", "Sign in"], ["signup", "Create account"], ["link", "Email link"]] as const).map(([m, label]) => (
          <button
            key={m}
            role="tab"
            aria-selected={mode === m}
            onClick={() => setMode(m)}
            className={cn("rounded-[9px] px-2 py-2 font-medium transition-colors", mode === m ? "bg-surface shadow-sm" : "text-muted hover:text-ink")}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === "link" ? (
        <ActionForm action={magicLink} className="space-y-4">
          <input type="hidden" name="next" value={next} />
          <Field label="Email">
            <Input name="email" type="email" autoComplete="email" required placeholder="you@college.edu" />
          </Field>
          <SubmitButton size="lg" className="w-full">Send me a sign-in link</SubmitButton>
        </ActionForm>
      ) : (
        <ActionForm action={passwordAuth} className="space-y-4" key={mode}>
          <input type="hidden" name="mode" value={mode} />
          <input type="hidden" name="next" value={next} />
          {mode === "signup" ? (
            <Field label="Full name">
              <Input name="name" autoComplete="name" required placeholder="Maya Fernandes" />
            </Field>
          ) : null}
          <Field label="Email">
            <Input name="email" type="email" autoComplete="email" required placeholder="you@college.edu" />
          </Field>
          <Field label="Password" hint={mode === "signup" ? "At least 8 characters" : undefined}>
            <Input name="password" type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} required minLength={8} />
          </Field>
          <SubmitButton size="lg" className="w-full">{mode === "signup" ? "Create my account" : "Sign in"}</SubmitButton>
        </ActionForm>
      )}
    </div>
  );
}
