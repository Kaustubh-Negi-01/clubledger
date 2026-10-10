-- Memberships, payments, events/tickets, merchandise store.

create table public.membership_plans (
  id bigserial primary key,
  code text not null unique,
  name text not null,
  dues_paise bigint not null check (dues_paise > 0),
  ticket_discount_bps int not null check (ticket_discount_bps between 0 and 10000),
  merch_discount_bps int not null check (merch_discount_bps between 0 and 10000),
  perks jsonb not null default '[]'::jsonb,
  is_active boolean not null default true
);

create table public.payments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id),
  purpose text not null check (purpose in ('DUES','TICKET','MERCH')),
  ref_id bigint not null,
  amount_paise bigint not null check (amount_paise > 0),
  status text not null default 'CREATED' check (status in ('CREATED','SUCCEEDED','FAILED','EXPIRED','REFUNDED')),
  fulfillment text not null default 'NONE' check (fulfillment in ('NONE','FULFILLED','UNFULFILLED','RESOLVED_REFUNDED')),
  term_id bigint not null references public.terms (id),
  succeeded_at timestamptz,
  settled_at timestamptz,
  refunded_at timestamptz,
  created_at timestamptz not null default now(),
  check (fulfillment <> 'FULFILLED' or status in ('SUCCEEDED','REFUNDED')),
  check (fulfillment <> 'UNFULFILLED' or status = 'SUCCEEDED')
);
create unique index ux_payments_live_target on public.payments (purpose, ref_id) where status in ('CREATED','SUCCEEDED');
create index ix_payments_user on public.payments (user_id);
create index ix_payments_status on public.payments (status, fulfillment);

create table public.memberships (
  id bigserial primary key,
  user_id uuid not null references public.profiles (id),
  plan_id bigint not null references public.membership_plans (id),
  membership_year text not null,
  status text not null check (status in ('PENDING','ACTIVE','EXPIRED','REVOKED','CANCELLED')),
  starts_at timestamptz not null,
  expires_at timestamptz not null,
  member_code text unique,
  qr_token text unique,
  payment_id uuid references public.payments (id),
  created_at timestamptz not null default now(),
  check (expires_at > starts_at),
  check (status <> 'ACTIVE' or (member_code is not null and qr_token is not null))
);
create unique index ux_member_user_year on public.memberships (user_id, membership_year) where status in ('PENDING','ACTIVE');
create index ix_memberships_expiry on public.memberships (status, expires_at);

-- ---- events & tickets ------------------------------------------------------
create table public.events (
  id bigserial primary key,
  term_id bigint not null references public.terms (id),
  title text not null,
  description text not null default '',
  venue text not null,
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  capacity int not null check (capacity > 0),
  member_price_paise bigint not null check (member_price_paise >= 0),
  public_price_paise bigint not null check (public_price_paise >= member_price_paise),
  max_per_order int not null default 4 check (max_per_order between 1 and 10),
  image_url text,
  status text not null default 'DRAFT' check (status in ('DRAFT','ON_SALE','CLOSED','CANCELLED')),
  created_at timestamptz not null default now(),
  check (ends_at > starts_at)
);

create table public.ticket_holds (
  id bigserial primary key,
  event_id bigint not null references public.events (id),
  user_id uuid not null references public.profiles (id),
  qty int not null check (qty between 1 and 10),
  unit_price_paise bigint not null check (unit_price_paise >= 0),
  price_tier text not null check (price_tier in ('MEMBER','PUBLIC')),
  status text not null check (status in ('HELD','CONSUMED','RELEASED','EXPIRED')),
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);
create index ix_holds_event on public.ticket_holds (event_id, status);
create index ix_holds_expiry on public.ticket_holds (status, expires_at);

create table public.tickets (
  id bigserial primary key,
  event_id bigint not null references public.events (id),
  hold_id bigint not null references public.ticket_holds (id),
  seat_index int not null check (seat_index between 1 and 10),
  user_id uuid not null references public.profiles (id),
  payment_id uuid references public.payments (id),
  code text not null unique,
  price_paise bigint not null check (price_paise >= 0),
  price_tier text not null check (price_tier in ('MEMBER','PUBLIC')),
  status text not null default 'ISSUED' check (status in ('ISSUED','USED','REFUNDED','VOID')),
  used_at timestamptz,
  used_by uuid references public.profiles (id),
  created_at timestamptz not null default now(),
  unique (hold_id, seat_index),
  check ((status = 'USED') = (used_at is not null)),
  check (price_paise = 0 or payment_id is not null),
  check (status <> 'VOID' or payment_id is null)
);
create index ix_tickets_event on public.tickets (event_id, status);
create index ix_tickets_user on public.tickets (user_id);
create index ix_tickets_payment on public.tickets (payment_id);

-- ---- store -----------------------------------------------------------------
create table public.products (
  id bigserial primary key,
  name text not null,
  description text not null default '',
  base_price_paise bigint not null check (base_price_paise > 0),
  image_url text,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create table public.variants (
  id bigserial primary key,
  product_id bigint not null references public.products (id),
  sku text not null unique,
  size text not null,
  physical_qty int not null check (physical_qty >= 0),
  reserved_qty int not null default 0 check (reserved_qty >= 0),
  unique (product_id, size),
  check (reserved_qty <= physical_qty)
);

create table public.merch_orders (
  id bigserial primary key,
  user_id uuid not null references public.profiles (id),
  status text not null check (status in ('RESERVED','PAID','PICKED_UP','CANCELLED','EXPIRED','REFUNDED')),
  expires_at timestamptz not null,
  total_paise bigint not null check (total_paise >= 0),
  price_tier text not null check (price_tier in ('MEMBER','PUBLIC')),
  picked_up_at timestamptz,
  picked_up_by uuid references public.profiles (id),
  created_at timestamptz not null default now()
);
create index ix_orders_user on public.merch_orders (user_id);
create index ix_orders_expiry on public.merch_orders (status, expires_at);

create table public.merch_order_items (
  id bigserial primary key,
  order_id bigint not null references public.merch_orders (id),
  variant_id bigint not null references public.variants (id),
  qty int not null check (qty between 1 and 10),
  unit_price_paise bigint not null check (unit_price_paise > 0),
  unique (order_id, variant_id)
);
