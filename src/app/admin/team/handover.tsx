"use client";

import { ActionForm, SubmitButton } from "@/components/ui/action-form";
import { Field, Select, Textarea } from "@/components/ui/field";
import { handoverAction } from "@/app/actions/staff";

export function HandoverForm({ people, mine }: { people: { id: string; name: string }[]; mine: { role: string; label: string }[] }) {
  return (
    <ActionForm action={handoverAction} className="space-y-4">
      <Field label="Hand over to">
        <Select name="to" required defaultValue=""><option value="" disabled>Choose a person</option>{people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select>
      </Field>
      <fieldset>
        <legend className="mb-2 text-sm font-medium">Roles to hand over</legend>
        <div className="flex flex-wrap gap-4">
          {mine.map((m) => (
            <label key={m.role} className="flex items-center gap-2 text-[15px]"><input type="checkbox" name="roles" value={m.role} className="size-4 accent-[var(--accent)]" /> {m.label}</label>
          ))}
        </div>
      </fieldset>
      <Field label="Notes for the next officer"><Textarea name="notes" className="min-h-20" placeholder="Where the receipts are kept, vendors to call..." /></Field>
      <SubmitButton variant="secondary">Record handover</SubmitButton>
    </ActionForm>
  );
}
