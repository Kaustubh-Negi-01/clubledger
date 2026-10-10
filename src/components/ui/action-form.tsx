"use client";

import { useActionState, useEffect, useRef } from "react";
import { useFormStatus } from "react-dom";
import { toast } from "sonner";
import { CircleNotch } from "@phosphor-icons/react";
import { Button } from "./button";
import { cn } from "@/lib/cn";
import type { ActionState } from "@/lib/action";

type FormAction = (prev: ActionState, formData: FormData) => Promise<ActionState>;

export function SubmitButton({
  children,
  pendingLabel,
  variant = "primary",
  size = "md",
  className,
}: {
  children: React.ReactNode;
  pendingLabel?: string;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant={variant} size={size} disabled={pending} className={className} aria-busy={pending}>
      {pending ? <CircleNotch size={18} className="animate-spin" aria-hidden /> : null}
      {pending && pendingLabel ? pendingLabel : children}
    </Button>
  );
}

/** A form wired to a server action: inline error, success toast, optional reset. */
export function ActionForm({
  action,
  children,
  className,
  reset = false,
}: {
  action: FormAction;
  children: React.ReactNode;
  className?: string;
  reset?: boolean;
}) {
  const [state, formAction] = useActionState(action, {} as ActionState);
  const ref = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (!state.nonce) return;
    if (state.ok) {
      if (state.message) toast.success(state.message);
      if (reset) ref.current?.reset();
    } else if (state.error) {
      toast.error(state.error);
    }
  }, [state, reset]);
  return (
    <form ref={ref} action={formAction} className={className}>
      {children}
      {state.error ? (
        <p role="alert" className="mt-3 rounded-ctl bg-bad-soft px-3.5 py-2.5 text-sm text-bad">
          {state.error}
        </p>
      ) : null}
    </form>
  );
}

/** One-click server action (refund, approve, pick up...) with optional confirmation. */
export function ActionButton({
  action,
  children,
  confirm,
  variant = "secondary",
  size = "sm",
  className,
}: {
  action: () => Promise<ActionState>;
  children: React.ReactNode;
  confirm?: string;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  className?: string;
}) {
  const [state, formAction] = useActionState(async () => action(), {} as ActionState);
  useEffect(() => {
    if (!state.nonce) return;
    if (state.ok) toast.success(state.message ?? "Done");
    else if (state.error) toast.error(state.error);
  }, [state]);
  return (
    <form
      action={formAction}
      className={cn("inline-block", className)}
      onSubmit={(e) => {
        if (confirm && !window.confirm(confirm)) e.preventDefault();
      }}
    >
      <SubmitButton variant={variant} size={size}>
        {children}
      </SubmitButton>
    </form>
  );
}
