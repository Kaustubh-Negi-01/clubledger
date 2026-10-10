-- Fundraisers/tasks, expenses/receipts, announcements/mail, term close and handover.

create table public.fundraisers (
  id bigserial primary key,
  term_id bigint not null references public.terms (id),
  title text not null,
  description text not null default '',
  goal_paise bigint check (goal_paise is null or goal_paise > 0),
  status text not null default 'PLANNING' check (status in ('PLANNING','ACTIVE','DONE','CANCELLED')),
  created_at timestamptz not null default now()
);

create table public.tasks (
  id bigserial primary key,
  fundraiser_id bigint not null references public.fundraisers (id),
  title text not null,
  owner_id uuid references public.profiles (id),
  due_on date,
  status text not null default 'TODO' check (status in ('TODO','DOING','DONE','BLOCKED')),
  created_at timestamptz not null default now(),
  unique (id, fundraiser_id)
);
create index ix_tasks_fundraiser on public.tasks (fundraiser_id, status);

create table public.expenses (
  id bigserial primary key,
  submitter_id uuid not null references public.profiles (id),
  term_id bigint not null references public.terms (id),
  category_code text not null references public.accounts (code),
  amount_paise bigint not null check (amount_paise > 0),
  description text not null,
  event_id bigint references public.events (id),
  fundraiser_id bigint references public.fundraisers (id),
  task_id bigint,
  status text not null default 'SUBMITTED' check (status in ('SUBMITTED','APPROVED','REJECTED','PAID','VOID')),
  decided_by uuid references public.profiles (id),
  decided_at timestamptz,
  decision_note text,
  paid_by uuid references public.profiles (id),
  paid_at timestamptz,
  created_at timestamptz not null default now(),
  foreign key (task_id, fundraiser_id) references public.tasks (id, fundraiser_id),
  check (task_id is null or fundraiser_id is not null)
);
create index ix_expenses_status on public.expenses (status);

create table public.receipts (
  id bigserial primary key,
  uploader_id uuid not null references public.profiles (id),
  expense_id bigint not null references public.expenses (id),
  storage_path text not null unique,
  original_name text not null,
  mime text not null check (mime in ('image/png','image/jpeg','application/pdf')),
  size_bytes int not null check (size_bytes between 1 and 5242880),
  created_at timestamptz not null default now()
);
create index ix_receipts_expense on public.receipts (expense_id);

-- ---- comms ------------------------------------------------------------------
create table public.announcements (
  id bigserial primary key,
  author_id uuid not null references public.profiles (id),
  term_id bigint not null references public.terms (id),
  title text not null,
  body text not null,
  status text not null default 'DRAFT' check (status in ('DRAFT','PUBLISHED')),
  published_at timestamptz,
  created_at timestamptz not null default now(),
  check ((status = 'PUBLISHED') = (published_at is not null))
);

create table public.subscribers (
  id bigserial primary key,
  email text not null,
  user_id uuid references public.profiles (id),
  status text not null default 'SUBSCRIBED' check (status in ('SUBSCRIBED','UNSUBSCRIBED')),
  unsub_token text not null unique default replace(gen_random_uuid()::text, '-', ''),
  subscribed_at timestamptz not null default now(),
  unsubscribed_at timestamptz
);
create unique index ux_subscribers_email on public.subscribers (lower(email));

create table public.mail_outbox (
  id bigserial primary key,
  dedupe_key text not null unique,
  to_email text not null,
  subject text not null,
  body text not null,
  kind text not null check (kind in ('ANNOUNCEMENT','RENEW_30D','RENEW_7D','EXPIRED')),
  ref_id bigint not null,
  status text not null default 'QUEUED' check (status in ('QUEUED','SENT','FAILED','SUPPRESSED')),
  suppressed_reason text,
  processed_at timestamptz,
  created_at timestamptz not null default now(),
  check ((status = 'SUPPRESSED') = (suppressed_reason is not null))
);
create index ix_outbox_status on public.mail_outbox (status);

create table public.mail_capture (
  id bigserial primary key,
  outbox_id bigint not null unique references public.mail_outbox (id),
  to_email text not null,
  subject text not null,
  body text not null,
  captured_at timestamptz not null default now()
);

-- ---- close & handover ---------------------------------------------------------
create table public.close_snapshots (
  id bigserial primary key,
  term_id bigint not null unique references public.terms (id),
  taken_by uuid not null references public.profiles (id),
  watermark_entry_id bigint not null,
  totals jsonb not null,
  content_sha256 text not null,
  taken_at timestamptz not null default now()
);
create or replace function public.trg_snapshot_immutable() returns trigger language plpgsql as $$
begin raise exception 'LEDGER|close snapshots are immutable'; end $$;
create trigger snapshot_immutable before update or delete on public.close_snapshots
  for each row execute function public.trg_snapshot_immutable();

create table public.officer_handover (
  id bigserial primary key,
  term_id bigint not null unique references public.terms (id),
  from_user uuid not null references public.profiles (id),
  to_user uuid not null references public.profiles (id),
  notes text,
  role_changes jsonb not null,
  completed_at timestamptz not null default now()
);
