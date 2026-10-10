"use client";

import { useActionState, useRef, useTransition } from "react";
import { useFormStatus } from "react-dom";
import { toast } from "sonner";
import { CircleNotch } from "@phosphor-icons/react";
import { Button } from "./button";
import { cn } from "@/lib/cn";
import type { ActionState } from "@/lib/action";

type FormAction = (prev: ActionState, formData: FormData) => Promise<ActionState>;

function announce(r: ActionState) {
  if (r.ok) {
    if (r.message) toast.success(r.message);
  } else if (r.error) {
    toast.error(r.error);
  }
}

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

/**
 * A form wired to a server action: inline error, success toast, optional reset.
 * Toasts fire inside the action promise, so they still appear when the revalidated page removes this form.
 */
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
  const ref = useRef<HTMLFormElement>(null);
  const [state, formAction] = useActionState(async (prev: ActionState, fd: FormData) => {
    const r = await action(prev, fd);
    announce(r);
    if (r.ok && reset) ref.current?.reset();
    return r;
  }, {} as ActionState);
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
  const [pending, start] = useTransition();
  return (
    <span className={cn("inline-block", className)}>
      <Button
        type="button"
        variant={variant}
        size={size}
        disabled={pending}
        aria-busy={pending}
        onClick={() => {
          if (confirm && !window.confirm(confirm)) return;
          start(async () => {
            announce(await action());
          });
        }}
      >
        {pending ? <CircleNotch size={18} className="animate-spin" aria-hidden /> : null}
        {children}
      </Button>
    </span>
  );
}
