import "server-only";
import { unstable_rethrow } from "next/navigation";
import { toAppError } from "./db/errors";

export interface ActionState {
  ok?: boolean;
  message?: string;
  error?: string;
  code?: string;
  nonce?: number;
}

/** Wraps a server action body: friendly errors for the UI, redirects pass through untouched. */
export async function run(fn: () => Promise<string | void>): Promise<ActionState> {
  try {
    const message = await fn();
    return { ok: true, message: message ?? undefined, nonce: Date.now() };
  } catch (e) {
    unstable_rethrow(e);
    const err = toAppError(e);
    return { ok: false, error: err.message, code: err.code, nonce: Date.now() };
  }
}
