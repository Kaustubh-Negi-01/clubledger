-- Double-entry ledger. Entries are created as DRAFT, lines added, then flipped to POSTED once.
-- Triggers (not just app code) make posted entries immutable and force balance.

create table public.accounts (
  code text primary key,
  name text not null,
  type text not null check (type in ('ASSET','LIABILITY','INCOME','EXPENSE'))
);

create table public.journal_entries (
  id bigserial primary key,
  term_id bigint not null references public.terms (id),
  entry_date timestamptz not null,
  source_type text not null check (source_type in ('payment','expense','adjustment')),
  source_id text not null,
  source_event text not null,
  memo text,
  status text not null default 'DRAFT' check (status in ('DRAFT','POSTED')),
  posted_at timestamptz,
  reverses_entry_id bigint references public.journal_entries (id),
  adjusts_term_id bigint references public.terms (id),
  created_at timestamptz not null default now(),
  unique (source_type, source_id, source_event),
  check ((status = 'POSTED') = (posted_at is not null)),
  check (adjusts_term_id is null or adjusts_term_id <> term_id),
  check (adjusts_term_id is null or source_type = 'adjustment'),
  check (source_event not like '%\_reversal' or reverses_entry_id is not null)
);
create unique index ux_entries_reversal on public.journal_entries (reverses_entry_id) where reverses_entry_id is not null;
create index ix_entries_term on public.journal_entries (term_id, entry_date);
create index ix_entries_source on public.journal_entries (source_type, source_id);

create table public.journal_lines (
  id bigserial primary key,
  entry_id bigint not null references public.journal_entries (id),
  account_code text not null references public.accounts (code),
  debit bigint not null default 0 check (debit >= 0),
  credit bigint not null default 0 check (credit >= 0),
  check ((debit = 0) <> (credit = 0))
);
create index ix_lines_entry on public.journal_lines (entry_id);
create index ix_lines_account on public.journal_lines (account_code);

-- ---- protection triggers -------------------------------------------------
create or replace function public.trg_entry_insert() returns trigger language plpgsql as $$
begin
  if new.status <> 'DRAFT' then raise exception 'LEDGER|entries must be inserted as DRAFT'; end if;
  if not exists (select 1 from public.terms where id = new.term_id and status = 'OPEN') then
    raise exception 'TERM_CLOSED|journal entries may only be posted into the open term';
  end if;
  if new.adjusts_term_id is not null
     and not exists (select 1 from public.terms where id = new.adjusts_term_id and status = 'CLOSED') then
    raise exception 'LEDGER|adjusts_term_id must reference a closed term';
  end if;
  return new;
end $$;
create trigger entry_insert before insert on public.journal_entries
  for each row execute function public.trg_entry_insert();

create or replace function public.trg_entry_update() returns trigger language plpgsql as $$
declare n int; d bigint; c bigint;
begin
  if old.status = 'POSTED' then raise exception 'LEDGER|posted entries are immutable'; end if;
  if new.term_id <> old.term_id or new.source_type <> old.source_type or new.source_id <> old.source_id
     or new.source_event <> old.source_event or new.reverses_entry_id is distinct from old.reverses_entry_id then
    raise exception 'LEDGER|entry key fields cannot change';
  end if;
  if new.status = 'POSTED' then
    select count(*), coalesce(sum(debit), 0), coalesce(sum(credit), 0) into n, d, c
      from public.journal_lines where entry_id = old.id;
    if n < 2 or d <> c or d = 0 then raise exception 'LEDGER|entry is not balanced (%/% over % lines)', d, c, n; end if;
    if not exists (select 1 from public.terms where id = new.term_id and status = 'OPEN') then
      raise exception 'TERM_CLOSED|term is closed';
    end if;
  end if;
  return new;
end $$;
create trigger entry_update before update on public.journal_entries
  for each row execute function public.trg_entry_update();

create or replace function public.trg_entry_delete() returns trigger language plpgsql as $$
begin
  if old.status = 'POSTED' then raise exception 'LEDGER|posted entries cannot be deleted'; end if;
  return old;
end $$;
create trigger entry_delete before delete on public.journal_entries
  for each row execute function public.trg_entry_delete();

create or replace function public.trg_line_write() returns trigger language plpgsql as $$
declare st text;
begin
  if tg_op = 'INSERT' then
    select status into st from public.journal_entries where id = new.entry_id;
    if st is distinct from 'DRAFT' then raise exception 'LEDGER|cannot add lines to a non-draft entry'; end if;
    return new;
  elsif tg_op = 'UPDATE' then
    if new.entry_id <> old.entry_id then raise exception 'LEDGER|lines cannot move between entries'; end if;
    select status into st from public.journal_entries where id = old.entry_id;
    if st is distinct from 'DRAFT' then raise exception 'LEDGER|posted lines are immutable'; end if;
    return new;
  else
    select status into st from public.journal_entries where id = old.entry_id;
    if st = 'POSTED' then raise exception 'LEDGER|posted lines cannot be deleted'; end if;
    return old;
  end if;
end $$;
create trigger line_write before insert or update or delete on public.journal_lines
  for each row execute function public.trg_line_write();

-- ---- posting API (internal) ---------------------------------------------
-- p_lines: [{"account":"1100","debit":500},{"account":"4100","credit":500}]
create or replace function public.post_entry(
  p_source_type text, p_source_id text, p_event text, p_memo text, p_lines jsonb,
  p_reverses bigint default null, p_adjusts bigint default null
) returns bigint language plpgsql security definer set search_path = public as $$
declare eid bigint; l jsonb;
begin
  select id into eid from public.journal_entries
   where source_type = p_source_type and source_id = p_source_id and source_event = p_event;
  if eid is not null then return eid; end if;

  insert into public.journal_entries (term_id, entry_date, source_type, source_id, source_event, memo, reverses_entry_id, adjusts_term_id)
  values (public.open_term_id(), public.app_now(), p_source_type, p_source_id, p_event, p_memo, p_reverses, p_adjusts)
  returning id into eid;

  for l in select * from jsonb_array_elements(p_lines) loop
    insert into public.journal_lines (entry_id, account_code, debit, credit)
    values (eid, l ->> 'account', coalesce((l ->> 'debit')::bigint, 0), coalesce((l ->> 'credit')::bigint, 0));
  end loop;

  update public.journal_entries set status = 'POSTED', posted_at = public.app_now() where id = eid;
  return eid;
end $$;

-- Exact mirror of an entry with debit/credit swapped. At most once per original (unique index).
create or replace function public.reverse_entry(p_entry bigint, p_memo text) returns bigint
language plpgsql security definer set search_path = public as $$
declare o public.journal_entries; eid bigint; lines jsonb;
begin
  select * into o from public.journal_entries where id = p_entry;
  select id into eid from public.journal_entries where reverses_entry_id = p_entry;
  if eid is not null then return eid; end if;
  select jsonb_agg(jsonb_build_object('account', account_code, 'debit', credit, 'credit', debit) order by id)
    into lines from public.journal_lines where entry_id = p_entry;
  return public.post_entry(o.source_type, o.source_id, o.source_event || '_reversal', p_memo, lines, p_entry, null);
end $$;

-- Reverse every not-yet-reversed entry of a source, newest first.
create or replace function public.reverse_all_for_source(p_type text, p_id text, p_memo text) returns int
language plpgsql security definer set search_path = public as $$
declare e record; n int := 0;
begin
  for e in
    select id from public.journal_entries je
     where je.source_type = p_type and je.source_id = p_id and je.reverses_entry_id is null
       and not exists (select 1 from public.journal_entries r where r.reverses_entry_id = je.id)
     order by je.id desc
  loop
    perform public.reverse_entry(e.id, p_memo);
    n := n + 1;
  end loop;
  return n;
end $$;

-- Live cumulative balance of an account across all terms (assets: Dr-Cr, liabilities: Cr-Dr, others by type).
create or replace function public.account_balance(p_code text, p_max_entry bigint default null) returns bigint
language sql stable security definer set search_path = public as $$
  select coalesce(sum(case a.type when 'ASSET' then l.debit - l.credit when 'EXPENSE' then l.debit - l.credit
                                  else l.credit - l.debit end), 0)::bigint
    from public.journal_lines l
    join public.journal_entries e on e.id = l.entry_id and e.status = 'POSTED'
    join public.accounts a on a.code = l.account_code
   where l.account_code = p_code and (p_max_entry is null or e.id <= p_max_entry)
$$;

create or replace function public.account_movement(p_code text, p_term bigint) returns bigint
language sql stable security definer set search_path = public as $$
  select coalesce(sum(case a.type when 'ASSET' then l.debit - l.credit when 'EXPENSE' then l.debit - l.credit
                                  else l.credit - l.debit end), 0)::bigint
    from public.journal_lines l
    join public.journal_entries e on e.id = l.entry_id and e.status = 'POSTED' and e.term_id = p_term
    join public.accounts a on a.code = l.account_code
   where l.account_code = p_code
$$;
