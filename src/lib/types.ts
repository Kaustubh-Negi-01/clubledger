export type Role = "admin" | "treasurer" | "organizer" | "door" | "store" | "comms";

export interface Membership {
  id: number; status: "ACTIVE" | "PENDING" | "EXPIRED"; membership_year: string; starts_at: string; expires_at: string;
  member_code: string | null; qr_token: string | null; plan_name: string; perks: string[];
  ticket_discount_bps: number; merch_discount_bps: number;
}
export interface Me { id: string; email: string; name: string; avatar_url: string | null; roles: Role[]; membership: Membership | null }

export interface EventRow {
  id: number; title: string; description: string; venue: string; starts_at: string; ends_at: string; capacity: number;
  member_price_paise: number; public_price_paise: number; image_url: string | null; status: "DRAFT" | "ON_SALE" | "CLOSED" | "CANCELLED";
  max_per_order: number; available: number; my_price: number; my_tier: "MEMBER" | "PUBLIC"; sold?: number; attended?: number;
}
export interface Variant { id: number; size: string; sku: string; available: number; physical: number; reserved: number }
export interface Product {
  id: number; name: string; description: string; base_price_paise: number; image_url: string | null; is_active: boolean;
  my_price: number; my_tier: "MEMBER" | "PUBLIC"; variants: Variant[];
}
export interface Ticket {
  id: number; code: string; seat_index: number; status: "ISSUED" | "USED" | "REFUNDED" | "VOID"; price_paise: number; price_tier: string;
  used_at: string | null; payment_id: string | null; event_id: number; title: string; venue: string; starts_at: string; ends_at: string; image_url: string | null;
}
export interface Payment { id: string; purpose: "DUES" | "TICKET" | "MERCH"; amount_paise: number; status: string; fulfillment: string; title: string; subtitle: string | null; hold_expires_at: string | null }
export interface Announcement { id: number; title: string; body: string; published_at: string; author: string }
export interface Order {
  id: number; status: string; total_paise: number; price_tier: string; expires_at: string; picked_up_at: string | null; created_at: string;
  payment_id: string | null; items: { name: string; size: string; qty: number; unit: number }[] | null;
}
export interface Task { id: number; title: string; status: "TODO" | "DOING" | "DONE" | "BLOCKED"; due_on: string | null; owner_id: string | null; owner: string | null }
export interface Fundraiser {
  id: number; title: string; description: string; goal_paise: number | null; status: string; spent_paise: number;
  tasks_total: number; tasks_done: number; tasks_overdue: number; tasks: Task[];
}
