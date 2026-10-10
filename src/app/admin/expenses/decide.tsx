"use client";

import { useRef } from "react";
import { toast } from "sonner";
import { ActionForm, SubmitButton } from "@/components/ui/action-form";
import { Input } from "@/components/ui/field";
import { decideExpenseAction } from "@/app/actions/staff";
import { Button } from "@/components/ui/button";

/** Approve and reject are two server actions sharing one note field. */
export function DecideForm({ id }: { id: number }) {
  const note = useRef<HTMLInputElement>(null);
  return (
    <div className="mt-4 flex flex-wrap items-end gap-2">
      <Input ref={note} name="note" placeholder="Optional note to the submitter" aria-label="Note" className="max-w-sm flex-1" />
      <form action={async () => {
        const fd = new FormData();
        fd.set("note", note.current?.value ?? "");
        const r = await decideExpenseAction(id, true, {}, fd);
        r.ok ? toast.success(r.message) : toast.error(r.error);
      }}>
        <Button type="submit" size="md">Approve</Button>
      </form>
      <form action={async () => {
        const fd = new FormData();
        fd.set("note", note.current?.value ?? "");
        const r = await decideExpenseAction(id, false, {}, fd);
        r.ok ? toast.success(r.message) : toast.error(r.error);
      }}>
        <Button type="submit" variant="danger" size="md">Reject</Button>
      </form>
    </div>
  );
}
