import { NextResponse } from "next/server";
import { rpc } from "@/lib/db";
import { getReceipt } from "@/lib/storage";

/** Receipts are private: the database decides who may read one, then the bytes are streamed as a download. */
export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const meta = await rpc<{ path: string; name: string; mime: string }>("api_receipt_path", { p_receipt: Number(id) });
    const bytes = await getReceipt(meta.path);
    return new NextResponse(Buffer.from(bytes), {
      headers: {
        "Content-Type": meta.mime,
        "Content-Disposition": `attachment; filename="${meta.name.replace(/"/g, "")}"`,
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
      },
    });
  } catch {
    return new NextResponse("Not found", { status: 404 });
  }
}
