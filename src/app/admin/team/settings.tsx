"use client";

import { ActionForm, ActionButton, SubmitButton } from "@/components/ui/action-form";
import { Field, Input } from "@/components/ui/field";
import { setConfigAction } from "@/app/actions/staff";

export function SettingsForm({ simulated, domains }: { simulated: boolean; domains: string }) {
  return (
    <div className="grid gap-8 md:grid-cols-2">
      <div>
        <p className="font-medium">Payments</p>
        <p className="mt-1 text-sm leading-relaxed text-muted">
          {simulated
            ? "Simulated payments are ON: any signed-in person can confirm their own checkout. That is right for a demo or a pilot with no real money. Switch it off before a real payment gateway goes live."
            : "Simulated payments are OFF: checkouts can only be confirmed by the payment gateway."}
        </p>
        <div className="mt-4">
          <ActionButton action={setConfigAction.bind(null, "simulated_payments", simulated ? "false" : "true")} variant={simulated ? "danger" : "secondary"} size="md" confirm={simulated ? "Turn simulated payments off? Nobody will be able to pay until a gateway is connected." : "Turn simulated payments on?"}>
            {simulated ? "Turn simulated payments off" : "Turn simulated payments on"}
          </ActionButton>
        </div>
      </div>
      <ActionForm action={setConfigAction.bind(null, "allowed_email_domains")} className="space-y-3">
        <Field label="Who may sign up" hint="Comma separated email domains, for example college.edu. Leave empty to allow anyone. Enforced in the database.">
          <Input name="value" defaultValue={domains} placeholder="college.edu" />
        </Field>
        <SubmitButton variant="secondary">Save</SubmitButton>
      </ActionForm>
    </div>
  );
}
