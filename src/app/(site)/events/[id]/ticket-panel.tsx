"use client";

import { useState } from "react";
import { Minus, Plus } from "@phosphor-icons/react";
import { ActionForm, SubmitButton } from "@/components/ui/action-form";
import { holdTicketsAction } from "@/app/actions/member";
import { inr } from "@/lib/format";

export function TicketPanel({ eventId, available, max, unit }: { eventId: number; available: number; max: number; unit: number }) {
  const cap = Math.max(0, Math.min(max, available));
  const [qty, setQty] = useState(Math.min(1, cap));
  if (cap === 0) return <p className="rounded-ctl bg-bad-soft p-3.5 text-sm text-bad">This event is sold out.</p>;
  return (
    <ActionForm action={holdTicketsAction.bind(null, eventId)} className="space-y-4">
      <input type="hidden" name="qty" value={qty} />
      <div className="flex items-center justify-between rounded-ctl border border-line p-1.5">
        <button type="button" aria-label="Fewer tickets" disabled={qty <= 1} onClick={() => setQty((q) => q - 1)} className="grid size-10 place-items-center rounded-[9px] hover:bg-surface-2 disabled:opacity-40">
          <Minus size={18} />
        </button>
        <div className="text-center" aria-live="polite">
          <p className="num text-xl font-semibold">{qty}</p>
          <p className="text-xs text-muted">{qty === 1 ? "ticket" : "tickets"}</p>
        </div>
        <button type="button" aria-label="More tickets" disabled={qty >= cap} onClick={() => setQty((q) => q + 1)} className="grid size-10 place-items-center rounded-[9px] hover:bg-surface-2 disabled:opacity-40">
          <Plus size={18} />
        </button>
      </div>
      <div className="flex items-baseline justify-between text-[15px]">
        <span className="text-muted">Total</span>
        <span className="num text-xl font-semibold">{unit === 0 ? "Free" : inr(unit * qty)}</span>
      </div>
      <SubmitButton size="lg" className="w-full" pendingLabel="Holding your seats">
        {unit === 0 ? "Reserve free tickets" : "Hold seats and pay"}
      </SubmitButton>
      {unit > 0 ? <p className="text-center text-xs text-muted">Seats are held for 10 minutes while you pay.</p> : null}
    </ActionForm>
  );
}
