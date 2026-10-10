import "server-only";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, normalize } from "node:path";
import { createClient } from "@supabase/supabase-js";
import { isDemo } from "./db";

const BUCKET = "receipts";
const LOCAL_ROOT = join(process.cwd(), ".data", "receipts");

function serviceClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) throw new Error("Receipt storage needs SUPABASE_SERVICE_ROLE_KEY on the server.");
  return createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
}

function safeLocal(path: string) {
  const full = normalize(join(LOCAL_ROOT, path));
  if (!full.startsWith(LOCAL_ROOT)) throw new Error("Invalid path");
  return full;
}

export async function putReceipt(path: string, bytes: Uint8Array, mime: string): Promise<void> {
  if (isDemo) {
    const full = safeLocal(path);
    await mkdir(dirname(full), { recursive: true });
    await writeFile(full, bytes);
    return;
  }
  const sb = serviceClient();
  await sb.storage.createBucket(BUCKET, { public: false, fileSizeLimit: 5 * 1024 * 1024 }).catch(() => undefined);
  const { error } = await sb.storage.from(BUCKET).upload(path, bytes, { contentType: mime, upsert: false });
  if (error) throw new Error(error.message);
}

export async function getReceipt(path: string): Promise<Uint8Array> {
  if (isDemo) return new Uint8Array(await readFile(safeLocal(path)));
  const { data, error } = await serviceClient().storage.from(BUCKET).download(path);
  if (error || !data) throw new Error(error?.message ?? "Missing file");
  return new Uint8Array(await data.arrayBuffer());
}

/** Magic-byte check: the declared type must match the file's real content. */
export function sniffMime(bytes: Uint8Array): "image/png" | "image/jpeg" | "application/pdf" | null {
  const b = bytes;
  if (b.length > 8 && b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) return "image/png";
  if (b.length > 3 && b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return "image/jpeg";
  if (b.length > 4 && b[0] === 0x25 && b[1] === 0x50 && b[2] === 0x44 && b[3] === 0x46) return "application/pdf";
  return null;
}
