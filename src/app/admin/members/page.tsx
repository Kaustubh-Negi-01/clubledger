import type { Metadata } from "next";
import { rpc } from "@/lib/db";
import { dateOnly } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";

export const metadata: Metadata = { title: "Members" };

interface Row { id: string; full_name: string; email: string; created_at: string; membership: string | null; expires_at: string | null; member_code: string | null; roles: string[] }

export default async function MembersPage() {
  const rows = await rpc<Row[]>("api_members_admin");
  const active = rows.filter((r) => r.membership === "ACTIVE").length;
  return (
    <>
      <PageHeader title="Members" description={`${active} active of ${rows.length} registered accounts. A registered account is not a membership: only paid dues unlock member prices.`} />
      <TableWrap>
        <Table>
          <thead><tr><Th>Name</Th><Th>Membership</Th><Th>Code</Th><Th>Valid until</Th><Th>Roles</Th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <Tr key={r.id}>
                <Td><p className="font-medium">{r.full_name}</p><p className="text-sm text-muted">{r.email}</p></Td>
                <Td>{r.membership ? <StatusBadge status={r.membership} /> : <Badge>Account only</Badge>}</Td>
                <Td num>{r.member_code ?? ""}</Td>
                <Td>{r.expires_at ? dateOnly(r.expires_at) : ""}</Td>
                <Td><div className="flex flex-wrap gap-1.5">{r.roles.map((x) => <Badge key={x} tone="accent">{x}</Badge>)}</div></Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </TableWrap>
    </>
  );
}
