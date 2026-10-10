"use client";

import { ActionForm, SubmitButton } from "@/components/ui/action-form";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { addReceiptAction, submitExpenseAction } from "@/app/actions/member";

const categories = [
  ["5000", "Events"],
  ["5010", "Merchandise stock"],
  ["5020", "Fundraiser"],
  ["5090", "Other"],
];

export function ExpenseForm({ fundraisers, events }: { fundraisers: { id: number; title: string }[]; events: { id: number; title: string }[] }) {
  return (
    <ActionForm action={submitExpenseAction} reset className="space-y-4">
      <Field label="What was it for?">
        <Textarea name="description" required minLength={4} maxLength={300} placeholder="Sound equipment hire for Open Mic" className="min-h-20" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Amount (rupees)">
          <Input name="amount" inputMode="decimal" required placeholder="450" />
        </Field>
        <Field label="Category">
          <Select name="category" defaultValue="5000">
            {categories.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </Field>
      </div>
      <Field label="Linked event (optional)">
        <Select name="event" defaultValue=""><option value="">None</option>{events.map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}</Select>
      </Field>
      <Field label="Linked fundraiser (optional)">
        <Select name="fundraiser" defaultValue=""><option value="">None</option>{fundraisers.map((f) => <option key={f.id} value={f.id}>{f.title}</option>)}</Select>
      </Field>
      <Field label="Receipt" hint="PNG, JPG or PDF, up to 5 MB. You can add it later.">
        <input type="file" name="receipt" accept="image/png,image/jpeg,application/pdf" className="block w-full text-sm file:mr-3 file:rounded-ctl file:border-0 file:bg-surface-2 file:px-4 file:py-2.5 file:text-sm file:font-medium hover:file:bg-line" />
      </Field>
      <SubmitButton className="w-full" pendingLabel="Submitting">Submit expense</SubmitButton>
    </ActionForm>
  );
}

export function ReceiptUpload({ expenseId }: { expenseId: number }) {
  return (
    <ActionForm action={addReceiptAction.bind(null, expenseId)} reset className="flex items-center gap-2">
      <input type="file" name="receipt" required accept="image/png,image/jpeg,application/pdf" aria-label="Receipt file" className="max-w-52 text-xs file:mr-2 file:rounded-ctl file:border-0 file:bg-surface-2 file:px-3 file:py-2 file:text-xs file:font-medium" />
      <SubmitButton variant="secondary" size="sm" pendingLabel="Uploading">Upload</SubmitButton>
    </ActionForm>
  );
}
