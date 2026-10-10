import type { Metadata } from "next";
import { requireRole } from "@/lib/session";
import { rpc } from "@/lib/db";
import { dateTime } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge } from "@/components/ui/badge";
import { ActionButton } from "@/components/ui/action-form";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { processOutboxAction } from "@/app/actions/staff";

export const metadata: Metadata = { title: "Mail log" };

interface Row { id: number; to_email: string; subject: string; kind: string; status: string; suppressed_reason: string | null; processed_at: string | null; created_at: string }

export default async function MailPage() {
  await requireRole("/admin/mail", "comms");
  const rows = await rpc<Row[]>("api_mail_admin");
  const queued = rows.filter((r) => r.status === "QUEUED").length;
  return (
    <>
      <PageHeader
        title="Mail log"
        description="Every email the club sends is queued here, re-checked against the recipient's subscription at send time, and recorded exactly once. This build captures mail locally; a provider such as Resend attaches at the same step."
        actions={<ActionButton action={processOutboxAction} variant="primary" size="md">Deliver {queued} queued</ActionButton>}
      />
      <TableWrap>
        <Table>
          <thead><tr><Th>To</Th><Th>Subject</Th><Th>Kind</Th><Th>Status</Th><Th>When</Th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <Tr key={r.id}>
                <Td>{r.to_email}</Td>
                <Td className="max-w-xs truncate">{r.subject}</Td>
                <Td className="text-sm text-muted">{r.kind.replace("_", " ").toLowerCase()}</Td>
                <Td><StatusBadge status={r.status} />{r.suppressed_reason ? <span className="ml-2 text-xs text-muted">{r.suppressed_reason.toLowerCase().replace("_", " ")}</span> : null}</Td>
                <Td className="text-sm text-muted">{dateTime(r.processed_at ?? r.created_at)}</Td>
              </Tr>
            ))}
            {rows.length === 0 ? <Tr><Td className="py-10 text-center text-muted">No mail yet.</Td><Td /><Td /><Td /><Td /></Tr> : null}
          </tbody>
        </Table>
      </TableWrap>
    </>
  );
}
