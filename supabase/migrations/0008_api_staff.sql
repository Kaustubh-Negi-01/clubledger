-- Officer-facing API: verification, check-in, catalog admin, payments, comms, tasks, expenses, team.

create or replace function public.api_verify_member(p_code text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare c text; m record;
begin
  perform public.require_any_role(array['door','organizer']);
  c := upper(trim(regexp_replace(coalesce(p_code, ''), '^CL-M:', '', 'i')));
  select m2.status, m2.starts_at, m2.expires_at, m2.membership_year, p.full_name, p.email, pl.name as plan,
         (m2.status = 'ACTIVE' and m2.starts_at <= public.app_now() and public.app_now() < m2.expires_at) as valid
    into m
    from public.memberships m2 join public.profiles p on p.id = m2.user_id join public.membership_plans pl on pl.id = m2.plan_id
   where m2.member_code = c or upper(m2.qr_token) = c
   order by m2.expires_at desc limit 1;
  if m.full_name is null then return jsonb_build_object('found', false); end if;
  return jsonb_build_object('found', true, 'name', m.full_name, 'plan', m.plan, 'year', m.membership_year,
                            'status', m.status, 'valid', m.valid, 'expires_at', m.expires_at);
end $$;

create or replace function public.api_checkin(p_event bigint, p_code text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_any_role(array['door','organizer']); c text; t public.tickets; h text; e public.events;
begin
  c := upper(trim(regexp_replace(coalesce(p_code, ''), '^CL-T:', '', 'i')));
  select * into t from public.tickets where code = c for update;
  if t.id is null then
    return jsonb_build_object('result', 'NOT_FOUND', 'message', 'No ticket matches that code');
  end if;
  select * into e from public.events where id = t.event_id;
  select full_name into h from public.profiles where id = t.user_id;
  if t.event_id <> p_event then
    return jsonb_build_object('result', 'WRONG_EVENT', 'message', 'This ticket is for ' || e.title, 'holder', h);
  end if;
  if t.status = 'USED' then
    return jsonb_build_object('result', 'ALREADY_USED', 'message', 'Already checked in', 'holder', h, 'used_at', t.used_at);
  end if;
  if t.status <> 'ISSUED' then
    return jsonb_build_object('result', 'INVALID', 'message', 'This ticket is ' || lower(t.status), 'holder', h);
  end if;
  update public.tickets set status = 'USED', used_at = public.app_now(), used_by = uid where id = t.id;
  return jsonb_build_object('result', 'OK', 'message', 'Checked in', 'holder', h, 'tier', t.price_tier, 'seat', t.seat_index);
end $$;

-- ---- events admin --------------------------------------------------------------------
create or replace function public.api_event_save(p_id bigint, p_title text, p_desc text, p_venue text, p_starts timestamptz,
  p_ends timestamptz, p_capacity int, p_member bigint, p_public bigint, p_max int, p_image text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('organizer'); e public.events;
begin
  if coalesce(trim(p_title), '') = '' or coalesce(trim(p_venue), '') = '' then perform public.fail('VALIDATION', 'Title and venue are required'); end if;
  if p_ends <= p_starts then perform public.fail('VALIDATION', 'The event must end after it starts'); end if;
  if p_capacity < 1 then perform public.fail('VALIDATION', 'Capacity must be at least 1'); end if;
  if p_member < 0 or p_public < p_member then perform public.fail('VALIDATION', 'Public price must be at least the member price'); end if;
  if p_id is null then
    insert into public.events (term_id, title, description, venue, starts_at, ends_at, capacity, member_price_paise, public_price_paise, max_per_order, image_url)
    values (public.open_term_id(), trim(p_title), coalesce(p_desc, ''), trim(p_venue), p_starts, p_ends, p_capacity, p_member, p_public,
            coalesce(p_max, 4), nullif(p_image, '')) returning * into e;
  else
    if p_capacity < (select count(*) from public.tickets where event_id = p_id and status in ('ISSUED','USED')) then
      perform public.fail('VALIDATION', 'Capacity cannot be lower than the tickets already sold');
    end if;
    update public.events set title = trim(p_title), description = coalesce(p_desc, ''), venue = trim(p_venue), starts_at = p_starts,
      ends_at = p_ends, capacity = p_capacity, member_price_paise = p_member, public_price_paise = p_public,
      max_per_order = coalesce(p_max, 4), image_url = nullif(p_image, '') where id = p_id returning * into e;
  end if;
  return jsonb_build_object('id', e.id);
end $$;

create or replace function public.api_event_set_status(p_id bigint, p_status text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('organizer'); e public.events; r record; refunded int := 0; voided int := 0;
begin
  if p_status not in ('DRAFT','ON_SALE','CLOSED','CANCELLED') then perform public.fail('VALIDATION', 'Unknown status'); end if;
  select * into e from public.events where id = p_id for update;
  if e.id is null then perform public.fail('NOT_FOUND', 'Event not found'); end if;
  if e.status = 'CANCELLED' then perform public.fail('VALIDATION', 'A cancelled event cannot change status'); end if;
  if p_status = 'CANCELLED' then
    -- paid tickets are refunded through the normal path; free tickets become VOID; used tickets are left for manual review
    for r in select distinct t.payment_id from public.tickets t
              where t.event_id = e.id and t.payment_id is not null and t.status = 'ISSUED'
                and not exists (select 1 from public.tickets u where u.payment_id = t.payment_id and u.status = 'USED') loop
      perform public.refund_payment_internal(r.payment_id); refunded := refunded + 1;
    end loop;
    update public.tickets set status = 'VOID' where event_id = e.id and payment_id is null and status = 'ISSUED';
    get diagnostics voided = row_count;
    update public.ticket_holds set status = 'RELEASED' where event_id = e.id and status = 'HELD';
  end if;
  update public.events set status = p_status where id = e.id;
  return jsonb_build_object('refunded_orders', refunded, 'voided_free', voided);
end $$;

create or replace function public.api_event_report(p_id bigint) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare r jsonb;
begin
  perform public.require_any_role(array['organizer','treasurer']);
  select jsonb_build_object(
    'sold', count(*) filter (where status in ('ISSUED','USED')),
    'attended', count(*) filter (where status = 'USED'),
    'no_shows', count(*) filter (where status = 'ISSUED'),
    'gross_paise', coalesce(sum(price_paise) filter (where status in ('ISSUED','USED','REFUNDED')), 0),
    'refunded_paise', coalesce(sum(price_paise) filter (where status = 'REFUNDED'), 0),
    'net_paise', coalesce(sum(price_paise) filter (where status in ('ISSUED','USED')), 0),
    'member_tickets', count(*) filter (where status in ('ISSUED','USED') and price_tier = 'MEMBER'),
    'public_tickets', count(*) filter (where status in ('ISSUED','USED') and price_tier = 'PUBLIC')
  ) into r from public.tickets where event_id = p_id;
  return r;
end $$;

create or replace function public.api_event_attendees(p_id bigint) returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.require_any_role(array['organizer','door']);
  return (select coalesce(jsonb_agg(to_jsonb(t) order by t.holder, t.seat_index), '[]'::jsonb) from (
    select tk.id, tk.code, tk.seat_index, tk.status, tk.price_tier, tk.used_at, p.full_name as holder, p.email
      from public.tickets tk join public.profiles p on p.id = tk.user_id where tk.event_id = p_id) t);
end $$;

-- ---- store admin ------------------------------------------------------------------------
create or replace function public.api_product_save(p_id bigint, p_name text, p_desc text, p_price bigint, p_image text, p_active boolean) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('store'); pr public.products;
begin
  if coalesce(trim(p_name), '') = '' or p_price is null or p_price <= 0 then perform public.fail('VALIDATION', 'Name and a positive price are required'); end if;
  if p_id is null then
    insert into public.products (name, description, base_price_paise, image_url, is_active)
    values (trim(p_name), coalesce(p_desc, ''), p_price, nullif(p_image, ''), coalesce(p_active, true)) returning * into pr;
  else
    update public.products set name = trim(p_name), description = coalesce(p_desc, ''), base_price_paise = p_price,
      image_url = nullif(p_image, ''), is_active = coalesce(p_active, true) where id = p_id returning * into pr;
  end if;
  return jsonb_build_object('id', pr.id);
end $$;

create or replace function public.api_variant_set_stock(p_product bigint, p_size text, p_physical int) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('store'); v public.variants;
begin
  if p_physical is null or p_physical < 0 then perform public.fail('VALIDATION', 'Stock cannot be negative'); end if;
  select * into v from public.variants where product_id = p_product and size = p_size for update;
  if v.id is null then
    insert into public.variants (product_id, sku, size, physical_qty)
    values (p_product, 'SKU-' || p_product || '-' || upper(p_size), p_size, p_physical) returning * into v;
  else
    if p_physical < v.reserved_qty then
      perform public.fail('VALIDATION', 'Stock cannot go below the ' || v.reserved_qty || ' units already reserved');
    end if;
    update public.variants set physical_qty = p_physical where id = v.id;
  end if;
  return jsonb_build_object('id', v.id);
end $$;

create or replace function public.api_orders_admin() returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.require_role('store');
  return (select coalesce(jsonb_agg(to_jsonb(t) order by t.id desc), '[]'::jsonb) from (
    select o.id, o.status, o.total_paise, o.price_tier, o.created_at, o.picked_up_at, p.full_name as buyer, p.email,
           (select jsonb_agg(jsonb_build_object('name', pr.name, 'size', v.size, 'qty', i.qty) order by i.id)
              from public.merch_order_items i join public.variants v on v.id = i.variant_id join public.products pr on pr.id = v.product_id
             where i.order_id = o.id) as items
      from public.merch_orders o join public.profiles p on p.id = o.user_id where o.status in ('PAID','PICKED_UP','RESERVED')) t);
end $$;

create or replace function public.api_order_pickup(p_order bigint) returns void
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('store'); o public.merch_orders; it record;
begin
  select * into o from public.merch_orders where id = p_order for update;
  if o.id is null then perform public.fail('NOT_FOUND', 'Order not found'); end if;
  if o.status <> 'PAID' then perform public.fail('VALIDATION', 'Only a paid order can be handed over'); end if;
  for it in select variant_id, qty from public.merch_order_items where order_id = o.id loop
    update public.variants set reserved_qty = reserved_qty - it.qty, physical_qty = physical_qty - it.qty where id = it.variant_id;
  end loop;
  update public.merch_orders set status = 'PICKED_UP', picked_up_at = public.app_now(), picked_up_by = uid where id = o.id;
end $$;

-- ---- payments admin ---------------------------------------------------------------------------
create or replace function public.api_payments_admin(p_problem boolean default false) returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.require_role('treasurer');
  return (select coalesce(jsonb_agg(to_jsonb(t) order by t.created_at desc), '[]'::jsonb) from (
    select p.id, p.purpose, p.amount_paise, p.status, p.fulfillment, p.created_at, p.succeeded_at, p.settled_at, pr.full_name as payer, pr.email
      from public.payments p join public.profiles pr on pr.id = p.user_id
     where (not p_problem) or (p.status = 'SUCCEEDED' and p.fulfillment = 'UNFULFILLED')
     order by p.created_at desc limit 200) t);
end $$;

create or replace function public.api_refund(p_id uuid) returns void
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('treasurer');
begin
  perform public.refund_payment_internal(p_id);
  insert into public.audit_log (actor, action, entity, entity_id) values (uid, 'refund', 'payment', p_id::text);
end $$;

create or replace function public.api_resolve_unfulfilled(p_id uuid, p_action text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('treasurer'); p public.payments; res text;
begin
  select * into p from public.payments where id = p_id for update;
  if p.id is null then perform public.fail('NOT_FOUND', 'Payment not found'); end if;
  if not (p.status = 'SUCCEEDED' and p.fulfillment = 'UNFULFILLED') then
    perform public.fail('VALIDATION', 'This payment has nothing to resolve');
  end if;
  if p_action = 'REFUND' then
    perform public.refund_payment_internal(p.id);
    return jsonb_build_object('resolved', 'REFUNDED');
  elsif p_action = 'FULFILL' then
    if p.term_id <> public.open_term_id() then
      perform public.fail('TERM_CLOSED', 'This payment belongs to a closed term. Refund it instead.');
    end if;
    res := public.fulfill_payment(p, true);
    if res <> 'FULFILLED' then
      perform public.fail(case split_part(res, ':', 2) when 'SOLD_OUT' then 'SOLD_OUT' when 'INSUFFICIENT_STOCK' then 'INSUFFICIENT_STOCK' else 'VALIDATION' end,
                          'Could not fulfill (' || lower(replace(split_part(res, ':', 2), '_', ' ')) || '). Refund instead.');
    end if;
    update public.payments set fulfillment = 'FULFILLED' where id = p.id;
    perform public.post_entry('payment', p.id::text, 'fulfilled_late', 'Late fulfillment',
      jsonb_build_array(jsonb_build_object('account', '2000', 'debit', p.amount_paise),
                        jsonb_build_object('account', public.income_account(p.purpose), 'credit', p.amount_paise)));
    return jsonb_build_object('resolved', 'FULFILLED');
  end if;
  perform public.fail('VALIDATION', 'Unknown action');
  return null;
end $$;

create or replace function public.api_settle() returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('treasurer'); p record; n int := 0; total bigint := 0;
begin
  for p in select id, amount_paise from public.payments where status = 'SUCCEEDED' and settled_at is null order by succeeded_at loop
    perform public.post_entry('payment', p.id::text, 'settled', 'Gateway payout',
      jsonb_build_array(jsonb_build_object('account', '1000', 'debit', p.amount_paise),
                        jsonb_build_object('account', '1100', 'credit', p.amount_paise)));
    update public.payments set settled_at = public.app_now() where id = p.id;
    n := n + 1; total := total + p.amount_paise;
  end loop;
  return jsonb_build_object('settled', n, 'amount_paise', total);
end $$;

-- ---- members & team ---------------------------------------------------------------------------
create or replace function public.api_members_admin() returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.require_any_role(array['organizer','treasurer','door']);
  return (select coalesce(jsonb_agg(to_jsonb(t) order by t.created_at desc), '[]'::jsonb) from (
    select p.id, p.full_name, p.email, p.created_at,
           (select m.status from public.memberships m where m.user_id = p.id and m.status in ('ACTIVE','PENDING','EXPIRED')
             order by (m.status = 'ACTIVE') desc, m.expires_at desc limit 1) as membership,
           (select m.expires_at from public.memberships m where m.user_id = p.id and m.status = 'ACTIVE' order by m.expires_at desc limit 1) as expires_at,
           (select m.member_code from public.memberships m where m.user_id = p.id and m.status = 'ACTIVE' order by m.expires_at desc limit 1) as member_code,
           coalesce((select jsonb_agg(role order by role) from public.user_roles where user_id = p.id and revoked_at is null), '[]'::jsonb) as roles
      from public.profiles p) t);
end $$;

create or replace function public.api_set_role(p_user uuid, p_role text, p_on boolean) returns void
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('admin');
begin
  if p_role not in ('admin','treasurer','organizer','door','store','comms') then perform public.fail('VALIDATION', 'Unknown role'); end if;
  if p_on then
    insert into public.user_roles (user_id, role) values (p_user, p_role) on conflict do nothing;
  else
    lock table public.user_roles in share row exclusive mode;   -- two admins cannot remove each other at the same instant
    if p_role = 'admin' and (select count(*) from public.user_roles where role = 'admin' and revoked_at is null and user_id <> p_user) = 0 then
      perform public.fail('VALIDATION', 'At least one admin must remain');
    end if;
    update public.user_roles set revoked_at = public.app_now() where user_id = p_user and role = p_role and revoked_at is null;
  end if;
  insert into public.audit_log (actor, action, entity, entity_id, detail)
  values (uid, case when p_on then 'role.grant' else 'role.revoke' end, 'user', p_user::text, jsonb_build_object('role', p_role));
end $$;

-- ---- comms admin ----------------------------------------------------------------------------------
create or replace function public.api_announcement_save(p_id bigint, p_title text, p_body text, p_publish boolean) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('comms'); a public.announcements; n int := 0;
begin
  if coalesce(trim(p_title), '') = '' or coalesce(trim(p_body), '') = '' then perform public.fail('VALIDATION', 'A title and message are required'); end if;
  if p_id is null then
    insert into public.announcements (author_id, term_id, title, body) values (uid, public.open_term_id(), trim(p_title), trim(p_body)) returning * into a;
  else
    select * into a from public.announcements where id = p_id for update;
    if a.id is null then perform public.fail('NOT_FOUND', 'Announcement not found'); end if;
    if a.status = 'PUBLISHED' then perform public.fail('VALIDATION', 'Published announcements cannot be edited'); end if;
    update public.announcements set title = trim(p_title), body = trim(p_body) where id = a.id returning * into a;
  end if;
  if p_publish then
    update public.announcements set status = 'PUBLISHED', published_at = public.app_now() where id = a.id and status = 'DRAFT';
    insert into public.mail_outbox (dedupe_key, to_email, subject, body, kind, ref_id)
    select 'announcement:' || a.id || ':' || lower(s.email), s.email, a.title, a.body, 'ANNOUNCEMENT', a.id
      from public.subscribers s where s.status = 'SUBSCRIBED'
    on conflict (dedupe_key) do nothing;
    get diagnostics n = row_count;
  end if;
  return jsonb_build_object('id', a.id, 'queued', n);
end $$;

create or replace function public.api_announcements_admin() returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.require_role('comms');
  return (select coalesce(jsonb_agg(to_jsonb(t) order by t.id desc), '[]'::jsonb) from (
    select a.id, a.title, a.body, a.status, a.published_at, a.created_at,
           (select count(*) from public.mail_outbox o where o.kind = 'ANNOUNCEMENT' and o.ref_id = a.id) as queued
      from public.announcements a) t);
end $$;

create or replace function public.api_subscribers_admin() returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.require_role('comms');
  return (select coalesce(jsonb_agg(to_jsonb(t) order by t.subscribed_at desc), '[]'::jsonb) from (
    select s.id, s.email, s.status, s.subscribed_at from public.subscribers s) t);
end $$;

-- Delivery: re-check eligibility at send time, record suppressions, capture exactly once.
-- (An external mail provider is attached later in the app layer; capture is the audit trail.)
create or replace function public.api_outbox_process(p_limit int default 100) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('comms'); o record; sent int := 0; supp int := 0; why text;
begin
  for o in select * from public.mail_outbox where status = 'QUEUED' order by id limit greatest(p_limit, 1) for update skip locked loop
    why := null;
    if o.kind = 'ANNOUNCEMENT' then
      if not exists (select 1 from public.subscribers s where lower(s.email) = lower(o.to_email) and s.status = 'SUBSCRIBED') then why := 'UNSUBSCRIBED'; end if;
    else
      if exists (select 1 from public.memberships m2 join public.memberships x on x.user_id = m2.user_id and x.id <> m2.id
                  where m2.id = o.ref_id and x.starts_at >= m2.expires_at and x.status in ('PENDING','ACTIVE')) then why := 'MEMBERSHIP_RENEWED';
      elsif exists (select 1 from public.memberships m2 where m2.id = o.ref_id and m2.status = 'REVOKED') then why := 'MEMBERSHIP_REVOKED';
      end if;
    end if;
    if why is not null then
      update public.mail_outbox set status = 'SUPPRESSED', suppressed_reason = why, processed_at = public.app_now() where id = o.id;
      supp := supp + 1;
    else
      insert into public.mail_capture (outbox_id, to_email, subject, body, captured_at) values (o.id, o.to_email, o.subject, o.body, public.app_now())
      on conflict (outbox_id) do nothing;
      update public.mail_outbox set status = 'SENT', processed_at = public.app_now() where id = o.id;
      sent := sent + 1;
    end if;
  end loop;
  return jsonb_build_object('sent', sent, 'suppressed', supp);
end $$;

create or replace function public.api_mail_admin() returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.require_role('comms');
  return (select coalesce(jsonb_agg(to_jsonb(t) order by t.id desc), '[]'::jsonb) from (
    select o.id, o.to_email, o.subject, o.body, o.kind, o.status, o.suppressed_reason, o.processed_at, o.created_at
      from public.mail_outbox o order by o.id desc limit 300) t);
end $$;

-- ---- fundraisers & tasks ----------------------------------------------------------------------------
create or replace function public.api_fundraiser_save(p_id bigint, p_title text, p_desc text, p_goal bigint, p_status text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('comms'); f public.fundraisers;
begin
  if coalesce(trim(p_title), '') = '' then perform public.fail('VALIDATION', 'Give the fundraiser a name'); end if;
  if p_id is null then
    insert into public.fundraisers (term_id, title, description, goal_paise, status)
    values (public.open_term_id(), trim(p_title), coalesce(p_desc, ''), p_goal, coalesce(p_status, 'PLANNING')) returning * into f;
  else
    update public.fundraisers set title = trim(p_title), description = coalesce(p_desc, ''), goal_paise = p_goal, status = coalesce(p_status, status)
     where id = p_id returning * into f;
  end if;
  return jsonb_build_object('id', f.id);
end $$;

create or replace function public.api_task_save(p_id bigint, p_fundraiser bigint, p_title text, p_owner uuid, p_due date, p_status text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('comms'); t public.tasks;
begin
  if coalesce(trim(p_title), '') = '' then perform public.fail('VALIDATION', 'Give the task a name'); end if;
  if p_id is null then
    insert into public.tasks (fundraiser_id, title, owner_id, due_on, status)
    values (p_fundraiser, trim(p_title), p_owner, p_due, coalesce(p_status, 'TODO')) returning * into t;
  else
    update public.tasks set title = trim(p_title), owner_id = p_owner, due_on = p_due, status = coalesce(p_status, status)
     where id = p_id returning * into t;
  end if;
  return jsonb_build_object('id', t.id);
end $$;

create or replace function public.api_fundraisers() returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.require_auth();
  return (select coalesce(jsonb_agg(to_jsonb(t) order by t.id desc), '[]'::jsonb) from (
    select f.id, f.title, f.description, f.goal_paise, f.status,
           coalesce((select sum(x.amount_paise) from public.expenses x where x.fundraiser_id = f.id and x.status in ('APPROVED','PAID')), 0) as spent_paise,
           (select count(*) from public.tasks k where k.fundraiser_id = f.id) as tasks_total,
           (select count(*) from public.tasks k where k.fundraiser_id = f.id and k.status = 'DONE') as tasks_done,
           (select count(*) from public.tasks k where k.fundraiser_id = f.id and k.status <> 'DONE' and k.due_on < (public.app_now() at time zone 'Asia/Kolkata')::date) as tasks_overdue,
           (select coalesce(jsonb_agg(jsonb_build_object('id', k.id, 'title', k.title, 'status', k.status, 'due_on', k.due_on,
                     'owner_id', k.owner_id, 'owner', p.full_name) order by k.due_on nulls last, k.id), '[]'::jsonb)
              from public.tasks k left join public.profiles p on p.id = k.owner_id where k.fundraiser_id = f.id) as tasks
      from public.fundraisers f) t);
end $$;

-- ---- expenses admin ----------------------------------------------------------------------------------
create or replace function public.api_expenses_admin() returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.require_role('treasurer');
  return (select coalesce(jsonb_agg(to_jsonb(t) order by t.id desc), '[]'::jsonb) from (
    select x.id, x.amount_paise, x.description, x.status, x.decision_note, x.created_at, a.name as category, p.full_name as submitter, x.submitter_id,
           (select coalesce(jsonb_agg(jsonb_build_object('id', r.id, 'name', r.original_name, 'mime', r.mime)), '[]'::jsonb)
              from public.receipts r where r.expense_id = x.id) as receipts
      from public.expenses x join public.accounts a on a.code = x.category_code join public.profiles p on p.id = x.submitter_id) t);
end $$;

create or replace function public.api_expense_decide(p_id bigint, p_approve boolean, p_note text) returns void
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('treasurer'); x public.expenses;
begin
  select * into x from public.expenses where id = p_id for update;
  if x.id is null then perform public.fail('NOT_FOUND', 'Expense not found'); end if;
  if x.status <> 'SUBMITTED' then perform public.fail('VALIDATION', 'This expense was already decided'); end if;
  if x.submitter_id = uid then perform public.fail('SELF_APPROVAL', 'You cannot approve your own expense'); end if;
  update public.expenses set status = case when p_approve then 'APPROVED' else 'REJECTED' end,
         decided_by = uid, decided_at = public.app_now(), decision_note = nullif(trim(coalesce(p_note, '')), '') where id = x.id;
  if p_approve then
    perform public.post_entry('expense', x.id::text, 'approved', 'Expense approved: ' || left(x.description, 80),
      jsonb_build_array(jsonb_build_object('account', x.category_code, 'debit', x.amount_paise),
                        jsonb_build_object('account', '2100', 'credit', x.amount_paise)));
  end if;
end $$;

create or replace function public.api_expense_pay(p_id bigint) returns void
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('treasurer'); x public.expenses;
begin
  select * into x from public.expenses where id = p_id for update;
  if x.id is null then perform public.fail('NOT_FOUND', 'Expense not found'); end if;
  if x.status <> 'APPROVED' then perform public.fail('VALIDATION', 'Only an approved expense can be paid'); end if;
  if not exists (select 1 from public.receipts where expense_id = x.id) then
    perform public.fail('VALIDATION', 'Attach at least one receipt before paying');
  end if;
  update public.expenses set status = 'PAID', paid_by = uid, paid_at = public.app_now() where id = x.id;
  perform public.post_entry('expense', x.id::text, 'paid', 'Reimbursement paid',
    jsonb_build_array(jsonb_build_object('account', '2100', 'debit', x.amount_paise),
                      jsonb_build_object('account', '1000', 'credit', x.amount_paise)));
end $$;

-- ---- deployment settings (admin only) ---------------------------------------------------------------
create or replace function public.api_config() returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.require_role('admin');
  return (select coalesce(jsonb_object_agg(key, value), '{}'::jsonb) from public.app_config);
end $$;

create or replace function public.api_set_config(p_key text, p_value text) returns void
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('admin');
begin
  if p_key not in ('simulated_payments', 'allowed_email_domains') then perform public.fail('VALIDATION', 'Unknown setting'); end if;
  if p_key = 'simulated_payments' and p_value not in ('true', 'false') then perform public.fail('VALIDATION', 'Use true or false'); end if;
  if p_key = 'allowed_email_domains' and p_value !~ '^[a-z0-9.,\- ]*$' then perform public.fail('VALIDATION', 'Use domains separated by commas'); end if;
  update public.app_config set value = lower(trim(p_value)), updated_at = public.app_now() where key = p_key;
  insert into public.audit_log (actor, action, entity, entity_id, detail) values (uid, 'config.set', 'app_config', p_key, jsonb_build_object('value', p_value));
end $$;
