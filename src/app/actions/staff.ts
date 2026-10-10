"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { rpc } from "@/lib/db";
import { Json } from "@/lib/db/json";
import { AppError, toAppError } from "@/lib/db/errors";
import { run, type ActionState } from "@/lib/action";
import { istInputToIso, toPaise } from "@/lib/format";

const s = (fd: FormData, k: string) => String(fd.get(k) ?? "").trim();
const n = (fd: FormData, k: string) => (fd.get(k) ? Number(fd.get(k)) : null);
function money(fd: FormData, k: string): number {
  const p = toPaise(fd.get(k));
  if (p === null) throw new AppError("VALIDATION", "Enter amounts in rupees, for example 650 or 650.50");
  return p;
}

// ---- door -----------------------------------------------------------------
export type CheckinResult = { result: string; message: string; holder?: string; tier?: string; seat?: number; used_at?: string };
export async function checkinAction(eventId: number, code: string): Promise<CheckinResult | { error: string }> {
  try {
    const r = await rpc<CheckinResult>("api_checkin", { p_event: eventId, p_code: code });
    revalidatePath("/admin/checkin");
    return r;
  } catch (e) {
    return { error: toAppError(e).message };
  }
}
export type VerifyResult = { found: boolean; name?: string; plan?: string; year?: string; status?: string; valid?: boolean; expires_at?: string };
export async function verifyMemberAction(code: string): Promise<VerifyResult | { error: string }> {
  try {
    return await rpc<VerifyResult>("api_verify_member", { p_code: code });
  } catch (e) {
    return { error: toAppError(e).message };
  }
}

// ---- events ---------------------------------------------------------------
export async function saveEventAction(id: number | null, _: ActionState, fd: FormData): Promise<ActionState> {
  return run(async () => {
    const res = await rpc<{ id: number }>("api_event_save", {
      p_id: id,
      p_title: s(fd, "title"),
      p_desc: s(fd, "description"),
      p_venue: s(fd, "venue"),
      p_starts: istInputToIso(s(fd, "starts_at")),
      p_ends: istInputToIso(s(fd, "ends_at")),
      p_capacity: Number(s(fd, "capacity")),
      p_member: money(fd, "member_price"),
      p_public: money(fd, "public_price"),
      p_max: n(fd, "max_per_order") ?? 4,
      p_image: s(fd, "image_url"),
    });
    revalidatePath("/admin/events");
    revalidatePath("/events");
    if (id === null) redirect(`/admin/events/${res.id}`);
    return "Event saved";
  });
}

export async function setEventStatusAction(id: number, status: string): Promise<ActionState> {
  return run(async () => {
    const r = await rpc<{ refunded_orders: number; voided_free: number }>("api_event_set_status", { p_id: id, p_status: status });
    revalidatePath("/admin/events");
    revalidatePath(`/admin/events/${id}`);
    revalidatePath("/events");
    if (status === "CANCELLED") return `Event cancelled. ${r.refunded_orders} order(s) refunded, ${r.voided_free} free ticket(s) voided.`;
    return status === "ON_SALE" ? "Tickets are on sale" : status === "CLOSED" ? "Sales closed" : "Event moved to draft";
  });
}

// ---- store ----------------------------------------------------------------
export async function saveProductAction(id: number | null, _: ActionState, fd: FormData): Promise<ActionState> {
  return run(async () => {
    const res = await rpc<{ id: number }>("api_product_save", {
      p_id: id,
      p_name: s(fd, "name"),
      p_desc: s(fd, "description"),
      p_price: money(fd, "price"),
      p_image: s(fd, "image_url"),
      p_active: fd.get("is_active") === "on",
    });
    revalidatePath("/admin/store");
    revalidatePath("/store");
    if (id === null) redirect(`/admin/store#product-${res.id}`);
    return "Product saved";
  });
}
export async function setStockAction(productId: number, _: ActionState, fd: FormData): Promise<ActionState> {
  return run(async () => {
    await rpc("api_variant_set_stock", { p_product: productId, p_size: s(fd, "size"), p_physical: Number(s(fd, "physical")) });
    revalidatePath("/admin/store");
    revalidatePath("/store");
    return "Stock updated";
  });
}
export async function pickupAction(orderId: number): Promise<ActionState> {
  return run(async () => {
    await rpc("api_order_pickup", { p_order: orderId });
    revalidatePath("/admin/orders");
    return "Marked as picked up";
  });
}

// ---- payments & finance -----------------------------------------------------------
export async function refundAction(paymentId: string): Promise<ActionState> {
  return run(async () => {
    await rpc("api_refund", { p_id: paymentId });
    revalidatePath("/admin/payments");
    revalidatePath("/admin/finance");
    return "Refunded in full and the ledger was reversed";
  });
}
export async function resolveAction(paymentId: string, action: "REFUND" | "FULFILL"): Promise<ActionState> {
  return run(async () => {
    await rpc("api_resolve_unfulfilled", { p_id: paymentId, p_action: action });
    revalidatePath("/admin/payments");
    revalidatePath("/admin/finance");
    return action === "REFUND" ? "Refunded" : "Fulfilled now";
  });
}
export async function settleAction(): Promise<ActionState> {
  return run(async () => {
    const r = await rpc<{ settled: number; amount_paise: number }>("api_settle");
    revalidatePath("/admin/payments");
    revalidatePath("/admin/finance");
    revalidatePath("/admin/close");
    return r.settled ? `Paid out ${r.settled} payment(s) to the bank` : "Nothing to settle";
  });
}

// ---- expenses ----------------------------------------------------------------------
export async function decideExpenseAction(id: number, approve: boolean, _: ActionState, fd: FormData): Promise<ActionState> {
  return run(async () => {
    await rpc("api_expense_decide", { p_id: id, p_approve: approve, p_note: s(fd, "note") });
    revalidatePath("/admin/expenses");
    return approve ? "Expense approved" : "Expense rejected";
  });
}
export async function payExpenseAction(id: number): Promise<ActionState> {
  return run(async () => {
    await rpc("api_expense_pay", { p_id: id });
    revalidatePath("/admin/expenses");
    revalidatePath("/admin/finance");
    return "Reimbursement paid and booked";
  });
}

// ---- comms ----------------------------------------------------------------------------
export async function saveAnnouncementAction(id: number | null, _: ActionState, fd: FormData): Promise<ActionState> {
  return run(async () => {
    const publish = fd.get("intent") === "publish";
    const r = await rpc<{ id: number; queued: number }>("api_announcement_save", { p_id: id, p_title: s(fd, "title"), p_body: s(fd, "body"), p_publish: publish });
    revalidatePath("/admin/announcements");
    revalidatePath("/announcements");
    revalidatePath("/");
    return publish ? `Published. ${r.queued} email(s) queued for delivery.` : "Draft saved";
  });
}
export async function processOutboxAction(): Promise<ActionState> {
  return run(async () => {
    const r = await rpc<{ sent: number; suppressed: number }>("api_outbox_process", { p_limit: 200 });
    revalidatePath("/admin/mail");
    return `${r.sent} delivered, ${r.suppressed} suppressed`;
  });
}

// ---- fundraisers ------------------------------------------------------------------------
export async function saveFundraiserAction(id: number | null, _: ActionState, fd: FormData): Promise<ActionState> {
  return run(async () => {
    const goal = s(fd, "goal") ? money(fd, "goal") : null;
    await rpc("api_fundraiser_save", { p_id: id, p_title: s(fd, "title"), p_desc: s(fd, "description"), p_goal: goal, p_status: s(fd, "status") || "PLANNING" });
    revalidatePath("/fundraisers");
    return "Fundraiser saved";
  });
}
export async function saveTaskAction(fundraiserId: number, _: ActionState, fd: FormData): Promise<ActionState> {
  return run(async () => {
    await rpc("api_task_save", {
      p_id: null,
      p_fundraiser: fundraiserId,
      p_title: s(fd, "title"),
      p_owner: s(fd, "owner") || null,
      p_due: s(fd, "due") || null,
      p_status: "TODO",
    });
    revalidatePath("/fundraisers");
    return "Task added";
  });
}

// ---- close, adjustments, team -------------------------------------------------------------------
export async function closeTermAction(): Promise<ActionState> {
  return run(async () => {
    const r = await rpc<{ closed: string; opened: string }>("api_close_term");
    revalidatePath("/admin", "layout");
    return `${r.closed} closed. ${r.opened} is now open.`;
  });
}
export async function adjustmentAction(_: ActionState, fd: FormData): Promise<ActionState> {
  return run(async () => {
    const amount = money(fd, "amount");
    const debit = s(fd, "debit");
    const credit = s(fd, "credit");
    if (!debit || !credit || debit === credit) throw new AppError("VALIDATION", "Choose two different accounts");
    await rpc("api_adjustment", {
      p_adjusts: Number(s(fd, "adjusts")),
      p_memo: s(fd, "memo"),
      p_lines: new Json([{ account: debit, debit: amount }, { account: credit, credit: amount }]),
    });
    revalidatePath("/admin/finance");
    return "Adjustment posted to the open term";
  });
}
export async function setRoleAction(userId: string, role: string, on: boolean): Promise<ActionState> {
  return run(async () => {
    await rpc("api_set_role", { p_user: userId, p_role: role, p_on: on });
    revalidatePath("/admin/team");
    return on ? "Role granted" : "Role removed";
  });
}
export async function handoverAction(_: ActionState, fd: FormData): Promise<ActionState> {
  return run(async () => {
    const roles = fd.getAll("roles").map(String);
    if (!roles.length) throw new AppError("VALIDATION", "Choose at least one role to hand over");
    await rpc("api_handover", { p_to: s(fd, "to"), p_roles: roles, p_notes: s(fd, "notes") });
    revalidatePath("/admin", "layout");
    return "Handover recorded. The new officer now holds those roles.";
  });
}
export async function processMaintenanceAction(): Promise<ActionState> {
  return run(async () => {
    const r = await rpc<Record<string, number>>("api_maintenance");
    revalidatePath("/admin", "layout");
    return `Expired ${r.holds_expired} holds, ${r.orders_expired} orders; queued ${r.reminders_queued} reminders.`;
  });
}

export async function setConfigAction(key: string, valueOrPrev: string | ActionState, fd?: FormData): Promise<ActionState> {
  return run(async () => {
    // Called as (key, value) from a button, or (key, prevState, formData) from a form.
    const value = typeof valueOrPrev === "string" ? valueOrPrev : String(fd?.get("value") ?? "");
    await rpc("api_set_config", { p_key: key, p_value: value });
    revalidatePath("/admin/team");
    return "Setting saved";
  });
}
