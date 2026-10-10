"use client";

import { useState } from "react";
import { Plus } from "@phosphor-icons/react";
import { ActionForm, SubmitButton } from "@/components/ui/action-form";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { saveFundraiserAction, saveTaskAction } from "@/app/actions/staff";

export function FundraiserForms() {
  const [open, setOpen] = useState(false);
  if (!open)
    return (
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <Plus size={18} /> New fundraiser
      </Button>
    );
  return (
    <ActionForm action={saveFundraiserAction.bind(null, null)} reset className="w-full max-w-xl space-y-3 rounded-card border border-line bg-surface p-5 shadow-card">
      <Field label="Name"><Input name="title" required placeholder="Monsoon Bake Sale" /></Field>
      <Field label="What is it for?"><Textarea name="description" className="min-h-20" /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Goal (rupees, optional)"><Input name="goal" inputMode="decimal" placeholder="15000" /></Field>
        <Field label="Status">
          <Select name="status" defaultValue="PLANNING"><option value="PLANNING">Planning</option><option value="ACTIVE">Active</option><option value="DONE">Done</option></Select>
        </Field>
      </div>
      <div className="flex gap-2">
        <SubmitButton>Create fundraiser</SubmitButton>
        <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Close</Button>
      </div>
    </ActionForm>
  );
}

export function TaskForm({ fundraiserId, people }: { fundraiserId: number; people: { id: string; name: string }[] }) {
  return (
    <ActionForm action={saveTaskAction.bind(null, fundraiserId)} reset className="mt-6 grid gap-3 border-t border-line pt-6 md:grid-cols-[1.5fr_1fr_1fr_auto] md:items-end">
      <Field label="New task"><Input name="title" required placeholder="Book the table" /></Field>
      <Field label="Owner">
        <Select name="owner" defaultValue=""><option value="">Unassigned</option>{people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select>
      </Field>
      <Field label="Due date"><Input name="due" type="date" /></Field>
      <SubmitButton variant="secondary">Add task</SubmitButton>
    </ActionForm>
  );
}
