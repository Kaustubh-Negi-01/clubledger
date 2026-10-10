import "server-only";
import { cache } from "react";
import { redirect } from "next/navigation";
import { rpc } from "./db";
import type { Me, Role } from "./types";

export const getMe = cache(async (): Promise<Me | null> => {
  try {
    return await rpc<Me | null>("api_me");
  } catch {
    return null;
  }
});

export async function requireMe(next = "/me"): Promise<Me> {
  const me = await getMe();
  if (!me) redirect(`/login?next=${encodeURIComponent(next)}`);
  return me;
}

export function hasRole(me: Me | null, ...roles: Role[]): boolean {
  if (!me) return false;
  return me.roles.includes("admin") || roles.some((r) => me.roles.includes(r));
}

export async function requireRole(next: string, ...roles: Role[]): Promise<Me> {
  const me = await requireMe(next);
  if (!hasRole(me, ...roles)) redirect("/me?denied=1");
  return me;
}

export function isStaff(me: Me | null): boolean {
  return !!me && me.roles.length > 0;
}
