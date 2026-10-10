"use client";

import { ActionForm, SubmitButton } from "@/components/ui/action-form";
import { Field, Input, Textarea } from "@/components/ui/field";
import { saveEventAction } from "@/app/actions/staff";
import { isoToIstInput, paiseToInput } from "@/lib/format";
import type { EventRow } from "@/lib/types";

export function EventForm({ event }: { event?: EventRow }) {
  return (
    <ActionForm action={saveEventAction.bind(null, event?.id ?? null)} className="space-y-4">
      <Field label="Title"><Input name="title" required defaultValue={event?.title} placeholder="Spring Gala" /></Field>
      <Field label="Description"><Textarea name="description" defaultValue={event?.description} className="min-h-24" /></Field>
      <Field label="Venue"><Input name="venue" required defaultValue={event?.venue} /></Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Starts (IST)"><Input name="starts_at" type="datetime-local" required defaultValue={event ? isoToIstInput(event.starts_at) : undefined} /></Field>
        <Field label="Ends (IST)"><Input name="ends_at" type="datetime-local" required defaultValue={event ? isoToIstInput(event.ends_at) : undefined} /></Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Capacity"><Input name="capacity" type="number" min={1} required defaultValue={event?.capacity ?? 100} /></Field>
        <Field label="Member price (rupees)"><Input name="member_price" inputMode="decimal" required defaultValue={event ? paiseToInput(event.member_price_paise) : "0"} /></Field>
        <Field label="Public price (rupees)"><Input name="public_price" inputMode="decimal" required defaultValue={event ? paiseToInput(event.public_price_paise) : "0"} /></Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Max tickets per order"><Input name="max_per_order" type="number" min={1} max={10} defaultValue={event?.max_per_order ?? 4} /></Field>
        <Field label="Image URL" hint="Optional"><Input name="image_url" type="url" defaultValue={event?.image_url ?? ""} placeholder="https://" /></Field>
      </div>
      <SubmitButton pendingLabel="Saving">{event ? "Save changes" : "Create event"}</SubmitButton>
    </ActionForm>
  );
}
