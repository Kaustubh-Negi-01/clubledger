import type { Metadata } from "next";
import { CheckCircle, XCircle } from "@phosphor-icons/react/dist/ssr";
import { rpc } from "@/lib/db";
import { toAppError } from "@/lib/db/errors";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Unsubscribe" };

export default async function UnsubscribePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  let email: string | null = null;
  let error: string | null = null;
  try {
    const r = await rpc<{ email: string }>("api_unsubscribe", { p_token: token });
    email = r.email;
  } catch (e) {
    error = toAppError(e).message;
  }
  return (
    <div className="mx-auto grid min-h-[60dvh] max-w-md content-center gap-5 px-4 py-20 text-center">
      {email ? <CheckCircle size={48} weight="fill" className="mx-auto text-ok" /> : <XCircle size={48} weight="fill" className="mx-auto text-bad" />}
      <h1 className="display text-4xl">{email ? "You are unsubscribed." : "That link did not work."}</h1>
      <p className="text-muted">{email ? `${email} will not get any more announcements.` : error}</p>
      <Button href="/" variant="secondary" className="mx-auto">Back to the club</Button>
    </div>
  );
}
