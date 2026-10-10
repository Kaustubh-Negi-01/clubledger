"use client";

import { ActionForm, SubmitButton } from "@/components/ui/action-form";
import { Field, Input, Textarea } from "@/components/ui/field";
import { saveAnnouncementAction } from "@/app/actions/staff";
import { Button } from "@/components/ui/button";
import { useFormStatus } from "react-dom";

function Publish() {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" name="intent" value="publish" disabled={pending}>
      Publish and email
    </Button>
  );
}

export function AnnouncementForm({ announcement }: { announcement?: { id: number; title: string; body: string } }) {
  return (
    <ActionForm action={saveAnnouncementAction.bind(null, announcement?.id ?? null)} reset={!announcement} className="space-y-3">
      <Field label="Headline"><Input name="title" required defaultValue={announcement?.title} placeholder="General body meeting, Thursday 6 pm" /></Field>
      <Field label="Message"><Textarea name="body" required defaultValue={announcement?.body} className="min-h-32" /></Field>
      <div className="flex flex-wrap gap-2">
        <Publish />
        <SubmitButton variant="secondary">Save draft</SubmitButton>
      </div>
    </ActionForm>
  );
}
