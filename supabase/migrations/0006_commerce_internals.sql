-- Internal (non-API) commerce logic: pricing, capacity, fulfillment, refunds, maintenance.
-- These functions are never granted to anon/authenticated; api_* wrappers call them.

create or replace function public.active_membership(p_uid uuid, p_at timestamptz)
returns public.memberships language sql stable security definer set search_path = public as $$
  select m.* from public.memberships m
   where m.user_id = p_uid and m.status = 'ACTIVE' and m.starts_at <= p_at and p_at < m.expires_at
   order by m.expires_at desc limit 1
$$;

create or replace function public.event_available(p_event bigint) returns int
language sql stable security definer set search_path = public as $$
  select e.capacity
       - coalesce((select sum(h.qty) from public.ticket_holds h
                    where h.event_id = e.id and h.status = 'HELD' and h.expires_at > public.app_now()), 0)::int
       - (select count(*) from public.tickets t where t.event_id = e.id and t.status in ('ISSUED','USED'))::int
    from public.events e where e.id = p_event
$$;

create or replace function public.ticket_price_for(p_event bigint, p_uid uuid, p_at timestamptz)
returns table (price bigint, tier text) language plpgsql stable security definer set search_path = public as $$
declare e public.events; m public.memberships; pl public.membership_plans;
begin
  select * into e from public.events where id = p_event;
  if p_uid is not null then select * into m from public.active_membership(p_uid, p_at); end if;
  if m.id is not null then
    select * into pl from public.membership_plans where id = m.plan_id;
    price := least(e.member_price_paise, (e.public_price_paise * (10000 - pl.ticket_discount_bps)) / 10000);
    tier := 'MEMBER';
  else
    price := e.public_price_paise; tier := 'PUBLIC';
  end if;
  return next;
end $$;

create or replace function public.merch_price_for(p_base bigint, p_uid uuid, p_at timestamptz)
returns table (price bigint, tier text) language plpgsql stable security definer set search_path = public as $$
declare m public.memberships; pl public.membership_plans;
begin
  if p_uid is not null then select * into m from public.active_membership(p_uid, p_at); end if;
  if m.id is not null then
    select * into pl from public.membership_plans where id = m.plan_id;
    price := (p_base * (10000 - pl.merch_discount_bps)) / 10000; tier := 'MEMBER';
  else
    price := p_base; tier := 'PUBLIC';
  end if;
  return next;
end $$;

create or replace function public.income_account(p_purpose text) returns text
language sql immutable as $$
  select case p_purpose when 'DUES' then '4000' when 'TICKET' then '4100' else '4200' end
$$;

-- ---- fulfillment handlers: return 'FULFILLED' or 'UNFULFILLABLE:<reason>' ----------
create or replace function public.fulfill_dues(p public.payments, p_manual boolean) returns text
language plpgsql security definer set search_path = public as $$
declare m public.memberships;
begin
  select * into m from public.memberships where id = p.ref_id for update;
  if m.status = 'PENDING' or (p_manual and m.status = 'CANCELLED'
       and not exists (select 1 from public.memberships x where x.user_id = m.user_id
                        and x.membership_year = m.membership_year and x.status in ('PENDING','ACTIVE') and x.id <> m.id)) then
    update public.memberships
       set status = 'ACTIVE', payment_id = p.id,
           member_code = 'CL-' || upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 8)),
           qr_token = replace(gen_random_uuid()::text, '-', '')
     where id = m.id;
    return 'FULFILLED';
  end if;
  return 'UNFULFILLABLE:TARGET_NOT_LIVE';
end $$;

create or replace function public.fulfill_tickets(p public.payments, p_manual boolean) returns text
language plpgsql security definer set search_path = public as $$
declare h public.ticket_holds; e public.events; i int; n int;
begin
  select * into e from public.events where id = (select event_id from public.ticket_holds where id = p.ref_id) for update;
  select * into h from public.ticket_holds where id = p.ref_id for update;
  if h.status = 'HELD' and h.expires_at <= public.app_now() then
    update public.ticket_holds set status = 'EXPIRED' where id = h.id;
    h.status := 'EXPIRED';
  end if;
  if e.status in ('CANCELLED','DRAFT') then return 'UNFULFILLABLE:EVENT_UNAVAILABLE'; end if;
  if h.status = 'HELD' then
    null;
  elsif p_manual and h.status = 'EXPIRED' then
    if public.event_available(h.event_id) < h.qty then return 'UNFULFILLABLE:SOLD_OUT'; end if;
  else
    return 'UNFULFILLABLE:TARGET_NOT_LIVE';
  end if;
  update public.ticket_holds set status = 'CONSUMED' where id = h.id and status in ('HELD','EXPIRED');
  get diagnostics n = row_count;
  if n <> 1 then raise exception 'INTERNAL|hold consumption guard failed'; end if;
  for i in 1 .. h.qty loop
    insert into public.tickets (event_id, hold_id, seat_index, user_id, payment_id, code, price_paise, price_tier)
    values (h.event_id, h.id, i, h.user_id, p.id,
            upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 14)), h.unit_price_paise, h.price_tier);
  end loop;
  return 'FULFILLED';
end $$;

create or replace function public.release_order(p_order bigint, p_to text) returns void
language plpgsql security definer set search_path = public as $$
declare it record;
begin
  update public.merch_orders set status = p_to where id = p_order and status in ('RESERVED','PAID');
  if not found then return; end if;
  for it in select variant_id, qty from public.merch_order_items where order_id = p_order loop
    update public.variants set reserved_qty = reserved_qty - it.qty where id = it.variant_id;
  end loop;
end $$;

create or replace function public.fulfill_merch(p public.payments, p_manual boolean) returns text
language plpgsql security definer set search_path = public as $$
declare o public.merch_orders; it record;
begin
  select * into o from public.merch_orders where id = p.ref_id for update;
  if o.status = 'RESERVED' and o.expires_at <= public.app_now() then
    perform public.release_order(o.id, 'EXPIRED');
    o.status := 'EXPIRED';
  end if;
  if o.status = 'RESERVED' then
    update public.merch_orders set status = 'PAID' where id = o.id;
    return 'FULFILLED';
  elsif p_manual and o.status in ('EXPIRED','CANCELLED') then
    for it in select i.variant_id, i.qty, v.physical_qty, v.reserved_qty
                from public.merch_order_items i join public.variants v on v.id = i.variant_id
               where i.order_id = o.id for update of v loop
      if it.physical_qty - it.reserved_qty < it.qty then return 'UNFULFILLABLE:INSUFFICIENT_STOCK'; end if;
    end loop;
    for it in select variant_id, qty from public.merch_order_items where order_id = o.id loop
      update public.variants set reserved_qty = reserved_qty + it.qty where id = it.variant_id;
    end loop;
    update public.merch_orders set status = 'PAID' where id = o.id;
    return 'FULFILLED';
  end if;
  return 'UNFULFILLABLE:TARGET_NOT_LIVE';
end $$;

create or replace function public.fulfill_payment(p public.payments, p_manual boolean) returns text
language sql security definer set search_path = public as $$
  select case p.purpose
    when 'DUES' then public.fulfill_dues(p, p_manual)
    when 'TICKET' then public.fulfill_tickets(p, p_manual)
    else public.fulfill_merch(p, p_manual) end
$$;

-- ---- refunds (full only; exact ledger reversals) -------------------------------
create or replace function public.refund_payment_internal(p_id uuid) returns void
language plpgsql security definer set search_path = public as $$
declare p public.payments; n int;
begin
  select * into p from public.payments where id = p_id for update;
  if p.id is null then perform public.fail('NOT_FOUND', 'Payment not found'); end if;
  if p.status <> 'SUCCEEDED' then perform public.fail('REFUND_BLOCKED', 'Only a received payment can be refunded'); end if;

  if p.fulfillment = 'FULFILLED' then
    if p.purpose = 'DUES' then
      update public.memberships set status = 'REVOKED' where id = p.ref_id;
    elsif p.purpose = 'TICKET' then
      select count(*) into n from public.tickets where payment_id = p.id and status <> 'ISSUED';
      if n > 0 then perform public.fail('REFUND_BLOCKED', 'A ticket from this order has already been used'); end if;
      update public.tickets set status = 'REFUNDED' where payment_id = p.id;
    else
      if (select status from public.merch_orders where id = p.ref_id) <> 'PAID' then
        perform public.fail('REFUND_BLOCKED', 'This order was already picked up');
      end if;
      perform public.release_order(p.ref_id, 'REFUNDED');
    end if;
    update public.payments set status = 'REFUNDED', refunded_at = public.app_now() where id = p.id;
  else
    update public.payments set status = 'REFUNDED', fulfillment = 'RESOLVED_REFUNDED', refunded_at = public.app_now() where id = p.id;
  end if;
  perform public.reverse_all_for_source('payment', p.id::text, 'Refund of payment ' || left(p.id::text, 8));
end $$;

-- ---- payment outcome (the simulated gateway) ---------------------------------
create or replace function public.apply_payment_success(p_id uuid) returns jsonb
language plpgsql security definer set search_path = public as $$
declare p public.payments; res text; fulfilled boolean;
begin
  select * into p from public.payments where id = p_id for update;
  if p.status in ('SUCCEEDED','REFUNDED') then
    return jsonb_build_object('outcome', 'NO_EFFECT', 'reason', 'REPEATED_NOTIFICATION', 'status', p.status);
  end if;
  if p.status = 'CREATED' then
    res := public.fulfill_payment(p, false);
  else
    res := 'UNFULFILLABLE:LATE_AFTER_' || p.status;
  end if;
  fulfilled := res = 'FULFILLED';
  update public.payments
     set status = 'SUCCEEDED', succeeded_at = public.app_now(),
         fulfillment = case when fulfilled then 'FULFILLED' else 'UNFULFILLED' end
   where id = p.id;
  perform public.post_entry('payment', p.id::text, 'received',
     case when fulfilled then 'Payment received' else 'Payment received, not fulfilled (' || split_part(res, ':', 2) || ')' end,
     jsonb_build_array(jsonb_build_object('account', '1100', 'debit', p.amount_paise),
                       jsonb_build_object('account', case when fulfilled then public.income_account(p.purpose) else '2000' end,
                                          'credit', p.amount_paise)));
  return jsonb_build_object('outcome', case when fulfilled then 'APPLIED' else 'APPLIED_UNFULFILLED' end,
                            'status', 'SUCCEEDED', 'fulfillment', case when fulfilled then 'FULFILLED' else 'UNFULFILLED' end,
                            'reason', case when fulfilled then null else split_part(res, ':', 2) end);
end $$;

-- ---- maintenance: expiry, reminders (idempotent, safe to run any time) ----------
create or replace function public.maintenance_run() returns jsonb
language plpgsql security definer set search_path = public as $$
declare n_holds int; n_orders int := 0; n_pay int; n_members int; n_mail int := 0; o record; r int;
begin
  update public.ticket_holds set status = 'EXPIRED' where status = 'HELD' and expires_at <= public.app_now();
  get diagnostics n_holds = row_count;

  for o in select id from public.merch_orders where status = 'RESERVED' and expires_at <= public.app_now() loop
    perform public.release_order(o.id, 'EXPIRED'); n_orders := n_orders + 1;
  end loop;

  update public.payments set status = 'EXPIRED'
   where status = 'CREATED' and created_at <= public.app_now() - interval '30 minutes';
  get diagnostics n_pay = row_count;

  update public.memberships m set status = 'CANCELLED'
   where m.status = 'PENDING' and exists (select 1 from public.payments p where p.purpose = 'DUES' and p.ref_id = m.id and p.status = 'EXPIRED');

  update public.memberships set status = 'EXPIRED' where status = 'ACTIVE' and expires_at <= public.app_now();
  get diagnostics n_members = row_count;

  -- renewal reminders: 30 days, 7 days, and on expiry; skip anyone who already has a later-year membership
  insert into public.mail_outbox (dedupe_key, to_email, subject, body, kind, ref_id)
  select 'reminder:' || k.kind || ':' || m.id, pr.email,
         case k.kind when 'EXPIRED' then 'Your Skyline membership has expired' else 'Your Skyline membership renews soon' end,
         case k.kind when 'EXPIRED' then 'Hi ' || pr.full_name || ', your membership expired. Renew in a minute to keep your member prices.'
              else 'Hi ' || pr.full_name || ', your membership ends on ' || to_char(m.expires_at at time zone 'Asia/Kolkata', 'DD Mon YYYY') || '. Renew now to keep your member prices.' end,
         k.kind, m.id
    from public.memberships m
    join public.profiles pr on pr.id = m.user_id
    cross join lateral (values ('RENEW_30D', interval '30 days'), ('RENEW_7D', interval '7 days'), ('EXPIRED', interval '0')) as k(kind, lead)
   where m.status in ('ACTIVE','EXPIRED')
     and public.app_now() >= m.expires_at - k.lead
     and public.app_now() < m.expires_at + interval '14 days'
     and (k.kind = 'EXPIRED') = (m.expires_at <= public.app_now())
     and not exists (select 1 from public.memberships x where x.user_id = m.user_id and x.id <> m.id
                      and x.starts_at >= m.expires_at and x.status in ('PENDING','ACTIVE'))
  on conflict (dedupe_key) do nothing;
  get diagnostics n_mail = row_count;

  return jsonb_build_object('holds_expired', n_holds, 'orders_expired', n_orders, 'payments_expired', n_pay,
                            'memberships_expired', n_members, 'reminders_queued', n_mail);
end $$;
