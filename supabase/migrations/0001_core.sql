-- ClubLedger core: profiles, roles, financial terms, clock and error helpers.
-- Every client call goes through SECURITY DEFINER api_* functions; tables are not exposed to the Data API.

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text not null,
  full_name text not null default '',
  avatar_url text,
  created_at timestamptz not null default now()
);
create unique index ux_profiles_email on public.profiles (lower(email));

create table public.user_roles (
  id bigserial primary key,
  user_id uuid not null references public.profiles (id) on delete cascade,
  role text not null check (role in ('admin','treasurer','organizer','door','store','comms')),
  granted_at timestamptz not null default now(),
  revoked_at timestamptz
);
create unique index ux_user_roles_live on public.user_roles (user_id, role) where revoked_at is null;

-- Financial terms (periods for the books). Not the same thing as the membership year.
create table public.terms (
  id bigserial primary key,
  label text not null unique,
  starts_at timestamptz not null,
  ends_at timestamptz,
  status text not null check (status in ('OPEN','CLOSED')),
  closed_at timestamptz,
  created_at timestamptz not null default now(),
  check ((status = 'OPEN' and ends_at is null and closed_at is null)
      or (status = 'CLOSED' and ends_at is not null and closed_at is not null and ends_at > starts_at))
);
create unique index ux_terms_one_open on public.terms (status) where status = 'OPEN';

create table public.audit_log (
  id bigserial primary key,
  actor uuid,
  action text not null,
  entity text not null,
  entity_id text,
  detail jsonb,
  created_at timestamptz not null default now()
);

-- Injectable clock: tests and the demo "time travel" set app.now_override; production never does.
create or replace function public.app_now() returns timestamptz
language sql stable as $$
  select coalesce(nullif(current_setting('app.now_override', true), '')::timestamptz, now())
$$;

-- Errors are raised as 'CODE|human message' so the app can show a friendly toast.
create or replace function public.fail(code text, msg text) returns void
language plpgsql as $$
begin
  raise exception '%', code || '|' || msg using errcode = 'P0001';
end $$;

create or replace function public.require_auth() returns uuid
language plpgsql stable as $$
declare uid uuid := auth.uid();
begin
  if uid is null then perform public.fail('AUTH_REQUIRED', 'Please sign in to continue'); end if;
  return uid;
end $$;

create or replace function public.has_role(r text) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.user_roles ur
    where ur.user_id = auth.uid() and ur.revoked_at is null and (ur.role = r or ur.role = 'admin')
  )
$$;

create or replace function public.require_role(r text) returns uuid
language plpgsql stable security definer set search_path = public as $$
declare uid uuid := public.require_auth();
begin
  if not public.has_role(r) then perform public.fail('FORBIDDEN', 'You do not have permission to do that'); end if;
  return uid;
end $$;

create or replace function public.require_any_role(rs text[]) returns uuid
language plpgsql stable security definer set search_path = public as $$
declare uid uuid := public.require_auth(); r text;
begin
  foreach r in array rs loop
    if public.has_role(r) then return uid; end if;
  end loop;
  perform public.fail('FORBIDDEN', 'You do not have permission to do that');
  return uid;
end $$;

create or replace function public.open_term_id() returns bigint
language sql stable security definer set search_path = public as $$
  select id from public.terms where status = 'OPEN'
$$;

-- Academic (membership) year: 1 Aug 00:00 IST to the next 1 Aug 00:00 IST, stored in UTC.
create or replace function public.academic_year_bounds(ts timestamptz)
returns table (label text, starts_at timestamptz, expires_at timestamptz)
language plpgsql immutable as $$
declare local_ts timestamp := ts at time zone 'Asia/Kolkata'; y int;
begin
  y := case when extract(month from local_ts) >= 8 then extract(year from local_ts)::int else extract(year from local_ts)::int - 1 end;
  label := y || '-' || lpad(((y + 1) % 100)::text, 2, '0');
  starts_at := make_timestamptz(y, 8, 1, 0, 0, 0, 'Asia/Kolkata');
  expires_at := make_timestamptz(y + 1, 8, 1, 0, 0, 0, 'Asia/Kolkata');
  return next;
end $$;

-- New auth user -> profile. The very first user becomes admin so a fresh deployment has an owner.
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email, full_name, avatar_url)
  values (new.id, coalesce(new.email, new.id::text || '@unknown.local'),
          coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name', split_part(coalesce(new.email, ''), '@', 1)),
          new.raw_user_meta_data ->> 'avatar_url')
  on conflict (id) do nothing;
  if not exists (select 1 from public.user_roles where role = 'admin' and revoked_at is null) then
    insert into public.user_roles (user_id, role) values (new.id, 'admin');
  end if;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();
