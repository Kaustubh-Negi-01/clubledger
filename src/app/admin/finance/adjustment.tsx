"use client";

import { ActionForm, SubmitButton } from "@/components/ui/action-form";
import { Field, Input, Select } from "@/components/ui/field";
import { adjustmentAction } from "@/app/actions/staff";

const accounts = [
  ["1000", "Cash and bank"], ["1100", "Payment clearing"], ["2000", "Unfulfilled obligation"], ["2100", "Reimbursements payable"],
  ["4000", "Dues income"], ["4100", "Ticket income"], ["4200", "Merchandise income"],
  ["5000", "Events expenses"], ["5010", "Merchandise stock"], ["5020", "Fundraiser expenses"], ["5090", "Other expenses"],
];

export function AdjustmentForm({ terms }: { terms: { id: number; label: string }[] }) {
  return (
    <ActionForm action={adjustmentAction} reset className="space-y-3">
      <Field label="Which closed term is this correcting?"><Select name="adjusts">{terms.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</Select></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Debit"><Select name="debit" defaultValue="">{<option value="" disabled>Choose</option>}{accounts.map(([c, n]) => <option key={c} value={c}>{c} {n}</option>)}</Select></Field>
        <Field label="Credit"><Select name="credit" defaultValue="">{<option value="" disabled>Choose</option>}{accounts.map(([c, n]) => <option key={c} value={c}>{c} {n}</option>)}</Select></Field>
      </div>
      <Field label="Amount (rupees)"><Input name="amount" inputMode="decimal" required /></Field>
      <Field label="Why?" hint="Required. Shown in the ledger forever."><Input name="memo" required minLength={4} /></Field>
      <SubmitButton variant="secondary">Post adjustment</SubmitButton>
    </ActionForm>
  );
}
