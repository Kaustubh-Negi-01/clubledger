"use client";

import { ActionForm, SubmitButton } from "@/components/ui/action-form";
import { Input } from "@/components/ui/field";
import { subscribeAction } from "@/app/actions/member";

export function SubscribeForm() {
  return (
    <ActionForm action={subscribeAction} reset className="flex flex-col gap-2 sm:flex-row">
      <label className="sr-only" htmlFor="sub-email">Email address</label>
      <Input id="sub-email" name="email" type="email" required placeholder="you@college.edu" autoComplete="email" className="sm:flex-1" />
      <SubmitButton pendingLabel="Joining">Get announcements</SubmitButton>
    </ActionForm>
  );
}
