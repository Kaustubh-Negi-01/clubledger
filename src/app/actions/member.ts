"use server";

import { randomUUID } from "node:crypto";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { rpc } from "@/lib/db";
import { Json } from "@/lib/db/json";
import { AppError } from "@/lib/db/errors";
import { run, type ActionState } from "@/lib/action";
import { requireMe } from "@/lib/session";
import { putReceipt, sniffMime } from "@/lib/storage";
import { toPaise } from "@/lib/format";

export async function joinAction(planId: number) {
  await requireMe("/join");
  const res = await rpc<{ payment_id: string }>("api_join", { p_plan: planId });
  redirect(`/pay/${res.payment_id}`);
}

export async function holdTicketsAction(eventId: number, _: ActionState, fd: FormData): Promise<ActionState> {
  return run(async () => {
    await requireMe(`/events/${eventId}`);
    const qty = Number(fd.get("qty") ?? 1);
    const res = await rpc<{ payment_id: string | null; free: boolean }>("api_hold_tickets", { p_event: eventId, p_qty: qty });
    revalidatePath(`/events/${eventId}`);
    redirect(res.free || !res.payment_id ? "/me/tickets?new=1" : `/pay/${res.payment_id}`);
  });
}

export async function reserveCartAction(_: ActionState, fd: FormData): Promise<ActionState> {
  return run(async () => {
    await requireMe("/store");
    const items: { variant_id: number; qty: number }[] = [];
    for (const [k, v] of fd.entries()) {
      const m = /^qty_(\d+)$/.exec(k);
      const qty = Number(v);
      if (m && Number.isFinite(qty) && qty > 0) items.push({ variant_id: Number(m[1]), qty });
    }
    if (!items.length) throw new AppError("VALIDATION", "Choose at least one size and quantity");
    const res = await rpc<{ payment_id: string }>("api_reserve_cart", { p_items: new Json(items) });
    redirect(`/pay/${res.payment_id}`);
  });
}

export async function cancelOrderAction(orderId: number): Promise<ActionState> {
  return run(async () => {
    await rpc("api_cancel_order", { p_order: orderId });
    revalidatePath("/me/orders");
    return "Order cancelled and stock released";
  });
}

export async function payOutcomeAction(paymentId: string, outcome: "success" | "fail"): Promise<ActionState> {
  return run(async () => {
    await requireMe(`/pay/${paymentId}`);
    const res = await rpc<{ outcome: string; reason?: string }>("api_pay_simulate", { p_id: paymentId, p_outcome: outcome });
    revalidatePath("/me", "layout");
    revalidatePath(`/pay/${paymentId}`);
    if (res.outcome === "NO_EFFECT") return "That payment was already recorded. Nothing was charged twice.";
    return outcome === "success" ? "Payment received" : "Payment marked as failed";
  });
}

export async function subscribeAction(_: ActionState, fd: FormData): Promise<ActionState> {
  return run(async () => {
    await rpc("api_subscribe", { p_email: String(fd.get("email") ?? "") });
    return "You are on the list. Announcements will land in your inbox.";
  });
}

export async function unsubscribeAction(token: string): Promise<ActionState> {
  return run(async () => {
    await rpc("api_unsubscribe", { p_token: token });
    return "You have been unsubscribed.";
  });
}

export async function submitExpenseAction(_: ActionState, fd: FormData): Promise<ActionState> {
  return run(async () => {
    const me = await requireMe("/me/expenses");
    const amount = toPaise(fd.get("amount"));
    if (amount === null || amount <= 0) throw new AppError("VALIDATION", "Enter the amount in rupees, for example 450 or 450.50");
    const fundraiser = fd.get("fundraiser") ? Number(fd.get("fundraiser")) : null;
    const event = fd.get("event") ? Number(fd.get("event")) : null;
    const created = await rpc<{ id: number }>("api_expense_submit", {
      p_category: String(fd.get("category") ?? ""),
      p_amount: amount,
      p_desc: String(fd.get("description") ?? ""),
      p_event: event,
      p_fundraiser: fundraiser,
      p_task: null,
    });
    const file = fd.get("receipt");
    if (file instanceof File && file.size > 0) await attachReceipt(me.id, created.id, file);
    revalidatePath("/me/expenses");
    return file instanceof File && file.size > 0 ? "Expense submitted with receipt" : "Expense submitted. Add a receipt so it can be paid.";
  });
}

export async function addReceiptAction(expenseId: number, _: ActionState, fd: FormData): Promise<ActionState> {
  return run(async () => {
    const me = await requireMe("/me/expenses");
    const file = fd.get("receipt");
    if (!(file instanceof File) || file.size === 0) throw new AppError("VALIDATION", "Choose a PNG, JPG or PDF file");
    await attachReceipt(me.id, expenseId, file);
    revalidatePath("/me/expenses");
    return "Receipt uploaded";
  });
}

async function attachReceipt(userId: string, expenseId: number, file: File) {
  if (file.size > 5 * 1024 * 1024) throw new AppError("UPLOAD_REJECTED", "That file is larger than 5 MB");
  const bytes = new Uint8Array(await file.arrayBuffer());
  const mime = sniffMime(bytes);
  if (!mime) throw new AppError("UPLOAD_REJECTED", "Upload a PNG, JPG or PDF. The file contents do not match.");
  const ext = mime === "application/pdf" ? "pdf" : mime === "image/png" ? "png" : "jpg";
  const path = `${userId}/${expenseId}/${randomUUID()}.${ext}`;
  const name = file.name.replace(/[^\w.\- ]+/g, "_").slice(0, 120) || `receipt.${ext}`;
  // Authorize and record first: the database decides whether this user may attach to this expense.
  await rpc("api_expense_add_receipt", { p_expense: expenseId, p_path: path, p_name: name, p_mime: mime, p_size: file.size });
  await putReceipt(path, bytes, mime);
}

export async function setTaskStatusAction(taskId: number, status: string): Promise<ActionState> {
  return run(async () => {
    await rpc("api_task_set_status", { p_task: taskId, p_status: status });
    revalidatePath("/fundraisers");
    revalidatePath("/me");
    return "Task updated";
  });
}
