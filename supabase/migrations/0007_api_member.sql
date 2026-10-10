-- Public and member-facing API. Every function returns jsonb and checks authorization itself.

create or replace function public.api_maintenance() returns jsonb
language sql security definer set search_path = public as $$ select public.maintenance_run() $$;

create or replace function public.api_me() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare uid uuid := auth.uid(); res jsonb;
begin
  if uid is null then return null; end if;
  select jsonb_build_object(
    'id', p.id, 'email', p.email, 'name', p.full_name, 'avatar_url', p.avatar_url,
    'roles', coalesce((select jsonb_agg(role order by role) from public.user_roles where user_id = p.id and revoked_at is null), '[]'::jsonb),
    'membership', (
      select to_jsonb(x) from (
        select m.id, m.status, m.membership_year, m.starts_at, m.expires_at, m.member_code, m.qr_token, pl.name as plan_name, pl.perks,
               pl.ticket_discount_bps, pl.merch_discount_bps
          from public.memberships m join public.membership_plans pl on pl.id = m.plan_id
         where m.user_id = p.id and m.status in ('ACTIVE','PENDING','EXPIRED')
         order by (m.status = 'ACTIVE' and m.starts_at <= public.app_now() and public.app_now() < m.expires_at) desc,
                  (m.status = 'ACTIVE') desc, m.expires_at desc limit 1) x)
  ) into res from public.profiles p where p.id = uid;
  return res;
end $$;

create or replace function public.api_plans() returns jsonb
language sql stable security definer set search_path = public as $$
  select coalesce(jsonb_agg(to_jsonb(p) order by dues_paise), '[]'::jsonb) from public.membership_plans p where is_active
$$;

-- ---- membership --------------------------------------------------------------
create or replace function public.api_join(p_plan bigint) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_auth(); pl public.membership_plans; cur record; nxt record; y record;
        act public.memberships; m public.memberships; pay public.payments;
begin
  select * into pl from public.membership_plans where id = p_plan and is_active;
  if pl.id is null then perform public.fail('NOT_FOUND', 'That plan is not available'); end if;
  select * into y from public.academic_year_bounds(public.app_now());
  select * into act from public.active_membership(uid, public.app_now());
  if act.id is not null then
    if public.app_now() < act.expires_at - interval '30 days' then
      perform public.fail('ALREADY_MEMBER', 'You are already a member. You can renew 30 days before it ends.');
    end if;
    select * into y from public.academic_year_bounds(act.expires_at);
  end if;
  select * into m from public.memberships
   where user_id = uid and membership_year = y.label and status in ('PENDING','ACTIVE');
  if m.id is not null and m.status = 'ACTIVE' then
    perform public.fail('ALREADY_MEMBER', 'You already have a membership for ' || y.label);
  end if;
  if m.id is null then
    insert into public.memberships (user_id, plan_id, membership_year, status, starts_at, expires_at)
    values (uid, pl.id, y.label, 'PENDING', y.starts_at, y.expires_at) returning * into m;
  end if;
  select * into pay from public.payments where purpose = 'DUES' and ref_id = m.id and status = 'CREATED';
  if pay.id is null then
    insert into public.payments (user_id, purpose, ref_id, amount_paise, term_id)
    values (uid, 'DUES', m.id, pl.dues_paise, public.open_term_id()) returning * into pay;
  end if;
  return jsonb_build_object('payment_id', pay.id, 'membership_id', m.id);
end $$;

-- ---- payments ------------------------------------------------------------------
create or replace function public.api_pay_get(p_id uuid) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_auth(); p public.payments; title text; sub text; ex timestamptz;
begin
  select * into p from public.payments where id = p_id and user_id = uid;
  if p.id is null then perform public.fail('NOT_FOUND', 'Payment not found'); end if;
  if p.purpose = 'DUES' then
    select 'Membership ' || m.membership_year, pl.name into title, sub
      from public.memberships m join public.membership_plans pl on pl.id = m.plan_id where m.id = p.ref_id;
  elsif p.purpose = 'TICKET' then
    select e.title || ' x ' || h.qty, e.venue, h.expires_at into title, sub, ex
      from public.ticket_holds h join public.events e on e.id = h.event_id where h.id = p.ref_id;
  else
    select 'Merchandise order #' || o.id, (select string_agg(pr.name || ' ' || v.size || ' x' || i.qty, ', ')
             from public.merch_order_items i join public.variants v on v.id = i.variant_id join public.products pr on pr.id = v.product_id
            where i.order_id = o.id), o.expires_at
      into title, sub, ex from public.merch_orders o where o.id = p.ref_id;
  end if;
  return jsonb_build_object('id', p.id, 'purpose', p.purpose, 'amount_paise', p.amount_paise, 'status', p.status,
    'fulfillment', p.fulfillment, 'title', title, 'subtitle', sub, 'hold_expires_at', ex, 'ref_id', p.ref_id);
end $$;

create or replace function public.api_pay_simulate(p_id uuid, p_outcome text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_auth(); p public.payments;
begin
  select * into p from public.payments where id = p_id and user_id = uid for update;
  if p.id is null then perform public.fail('NOT_FOUND', 'Payment not found'); end if;
  if p_outcome = 'fail' then
    if p.status = 'CREATED' then
      update public.payments set status = 'FAILED' where id = p.id;
      return jsonb_build_object('outcome', 'APPLIED', 'status', 'FAILED');
    end if;
    return jsonb_build_object('outcome', 'NO_EFFECT', 'status', p.status);
  elsif p_outcome = 'success' then
    return public.apply_payment_success(p.id);
  end if;
  perform public.fail('VALIDATION', 'Unknown outcome');
  return null;
end $$;

-- ---- events & tickets ------------------------------------------------------------
create or replace function public.api_events_list(p_all boolean default false) returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  if p_all then perform public.require_any_role(array['organizer','door','treasurer']); end if;
  return (select coalesce(jsonb_agg(to_jsonb(t) order by t.starts_at), '[]'::jsonb) from (
    select e.id, e.title, e.description, e.venue, e.starts_at, e.ends_at, e.capacity, e.member_price_paise, e.public_price_paise,
           e.image_url, e.status, e.max_per_order, public.event_available(e.id) as available,
           (select price from public.ticket_price_for(e.id, auth.uid(), public.app_now())) as my_price,
           (select tier from public.ticket_price_for(e.id, auth.uid(), public.app_now())) as my_tier,
           (select count(*) from public.tickets x where x.event_id = e.id and x.status in ('ISSUED','USED')) as sold,
           (select count(*) from public.tickets x where x.event_id = e.id and x.status = 'USED') as attended
      from public.events e
     where (p_all or (e.status in ('ON_SALE','CLOSED') and e.ends_at > public.app_now() - interval '1 day'))
  ) t);
end $$;

create or replace function public.api_event_get(p_id bigint) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare res jsonb;
begin
  select to_jsonb(t) into res from (
    select e.id, e.title, e.description, e.venue, e.starts_at, e.ends_at, e.capacity, e.member_price_paise, e.public_price_paise,
           e.image_url, e.status, e.max_per_order, public.event_available(e.id) as available,
           (select price from public.ticket_price_for(e.id, auth.uid(), public.app_now())) as my_price,
           (select tier from public.ticket_price_for(e.id, auth.uid(), public.app_now())) as my_tier
      from public.events e where e.id = p_id and (e.status <> 'DRAFT' or public.has_role('organizer'))) t;
  return res;
end $$;

create or replace function public.api_hold_tickets(p_event bigint, p_qty int) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_auth(); e public.events; h public.ticket_holds; pay public.payments;
        unit bigint; tier text; i int; avail int;
begin
  select * into e from public.events where id = p_event for update;
  if e.id is null or e.status <> 'ON_SALE' or e.ends_at <= public.app_now() then
    perform public.fail('NOT_ON_SALE', 'Tickets for this event are not on sale');
  end if;
  if p_qty is null or p_qty < 1 or p_qty > e.max_per_order then
    perform public.fail('VALIDATION', 'Choose between 1 and ' || e.max_per_order || ' tickets');
  end if;

  -- double-submit protection: reuse the user's own live hold + payment for this event
  select * into h from public.ticket_holds
   where event_id = e.id and user_id = uid and status = 'HELD' and expires_at > public.app_now() order by id desc limit 1;
  if h.id is not null then
    select * into pay from public.payments where purpose = 'TICKET' and ref_id = h.id and status = 'CREATED';
    if pay.id is not null and h.qty = p_qty then
      return jsonb_build_object('payment_id', pay.id, 'free', false, 'reused', true);
    end if;
    update public.ticket_holds set status = 'RELEASED' where id = h.id;
    update public.payments set status = 'EXPIRED' where purpose = 'TICKET' and ref_id = h.id and status = 'CREATED';
  end if;

  avail := public.event_available(e.id);
  if avail < p_qty then
    perform public.fail('SOLD_OUT', case when avail = 0 then 'This event is sold out' else 'Only ' || avail || ' seat' || case when avail = 1 then '' else 's' end || ' left' end);
  end if;
  select price, t.tier into unit, tier from public.ticket_price_for(e.id, uid, public.app_now()) t;

  if unit = 0 then
    insert into public.ticket_holds (event_id, user_id, qty, unit_price_paise, price_tier, status, expires_at)
    values (e.id, uid, p_qty, 0, tier, 'CONSUMED', public.app_now()) returning * into h;
    for i in 1 .. p_qty loop
      insert into public.tickets (event_id, hold_id, seat_index, user_id, payment_id, code, price_paise, price_tier)
      values (e.id, h.id, i, uid, null, upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 14)), 0, tier);
    end loop;
    return jsonb_build_object('payment_id', null, 'free', true);
  end if;

  insert into public.ticket_holds (event_id, user_id, qty, unit_price_paise, price_tier, status, expires_at)
  values (e.id, uid, p_qty, unit, tier, 'HELD', public.app_now() + interval '10 minutes') returning * into h;
  insert into public.payments (user_id, purpose, ref_id, amount_paise, term_id)
  values (uid, 'TICKET', h.id, unit * p_qty, public.open_term_id()) returning * into pay;
  return jsonb_build_object('payment_id', pay.id, 'free', false, 'expires_at', h.expires_at);
end $$;

create or replace function public.api_my_tickets() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare uid uuid := public.require_auth();
begin
  return (select coalesce(jsonb_agg(to_jsonb(t) order by t.starts_at desc, t.id), '[]'::jsonb) from (
    select tk.id, tk.code, tk.seat_index, tk.status, tk.price_paise, tk.price_tier, tk.used_at, tk.payment_id,
           e.id as event_id, e.title, e.venue, e.starts_at, e.ends_at, e.image_url
      from public.tickets tk join public.events e on e.id = tk.event_id where tk.user_id = uid) t);
end $$;

create or replace function public.api_ticket_get(p_code text) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare uid uuid := public.require_auth(); res jsonb;
begin
  select to_jsonb(t) into res from (
    select tk.id, tk.code, tk.seat_index, tk.status, tk.price_paise, tk.price_tier, tk.used_at,
           e.id as event_id, e.title, e.venue, e.starts_at, e.ends_at, e.image_url, p.full_name as holder
      from public.tickets tk join public.events e on e.id = tk.event_id join public.profiles p on p.id = tk.user_id
     where tk.code = p_code and tk.user_id = uid) t;
  return res;
end $$;

-- ---- store ---------------------------------------------------------------------------
create or replace function public.api_products_list(p_all boolean default false) returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  if p_all then perform public.require_role('store'); end if;
  return (select coalesce(jsonb_agg(to_jsonb(t) order by t.id), '[]'::jsonb) from (
    select p.id, p.name, p.description, p.base_price_paise, p.image_url, p.is_active,
           (select price from public.merch_price_for(p.base_price_paise, auth.uid(), public.app_now())) as my_price,
           (select tier from public.merch_price_for(p.base_price_paise, auth.uid(), public.app_now())) as my_tier,
           (select coalesce(jsonb_agg(jsonb_build_object('id', v.id, 'size', v.size, 'sku', v.sku,
                    'available', v.physical_qty - v.reserved_qty, 'physical', v.physical_qty, 'reserved', v.reserved_qty)
                    order by v.id), '[]'::jsonb) from public.variants v where v.product_id = p.id) as variants
      from public.products p where p_all or p.is_active) t);
end $$;

create or replace function public.api_reserve_cart(p_items jsonb) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_auth(); it jsonb; v public.variants; pr public.products; o public.merch_orders; pay public.payments;
        qty int; unit bigint; tier text := 'PUBLIC'; total bigint := 0; seen bigint[] := '{}'; vid bigint;
begin
  if p_items is null or jsonb_typeof(p_items) <> 'array' or jsonb_array_length(p_items) = 0 then
    perform public.fail('VALIDATION', 'Your cart is empty');
  end if;
  insert into public.merch_orders (user_id, status, expires_at, total_paise, price_tier)
  values (uid, 'RESERVED', public.app_now() + interval '15 minutes', 0, 'PUBLIC') returning * into o;

  for it in select * from jsonb_array_elements(p_items) order by (value ->> 'variant_id')::bigint loop
    vid := (it ->> 'variant_id')::bigint;
    qty := (it ->> 'qty')::int;
    if qty is null or qty < 1 or qty > 10 then perform public.fail('VALIDATION', 'Quantity must be between 1 and 10'); end if;
    if vid = any (seen) then perform public.fail('VALIDATION', 'Each size can appear once in the cart'); end if;
    seen := seen || vid;
    select * into v from public.variants where id = vid for update;
    if v.id is null then perform public.fail('NOT_FOUND', 'That size does not exist'); end if;
    select * into pr from public.products where id = v.product_id and is_active;
    if pr.id is null then perform public.fail('NOT_FOUND', 'That product is not available'); end if;
    if v.physical_qty - v.reserved_qty < qty then
      perform public.fail('INSUFFICIENT_STOCK', pr.name || ' (' || v.size || ') has only ' || (v.physical_qty - v.reserved_qty) || ' left');
    end if;
    update public.variants set reserved_qty = reserved_qty + qty where id = v.id;
    select price, t.tier into unit, tier from public.merch_price_for(pr.base_price_paise, uid, public.app_now()) t;
    insert into public.merch_order_items (order_id, variant_id, qty, unit_price_paise) values (o.id, v.id, qty, unit);
    total := total + unit * qty;
  end loop;

  update public.merch_orders set total_paise = total, price_tier = tier where id = o.id;
  insert into public.payments (user_id, purpose, ref_id, amount_paise, term_id)
  values (uid, 'MERCH', o.id, total, public.open_term_id()) returning * into pay;
  return jsonb_build_object('payment_id', pay.id, 'order_id', o.id, 'total_paise', total);
end $$;

create or replace function public.api_cancel_order(p_order bigint) returns void
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_auth(); o public.merch_orders;
begin
  select * into o from public.merch_orders where id = p_order and user_id = uid for update;
  if o.id is null then perform public.fail('NOT_FOUND', 'Order not found'); end if;
  if o.status <> 'RESERVED' then perform public.fail('VALIDATION', 'Only an unpaid order can be cancelled'); end if;
  perform public.release_order(o.id, 'CANCELLED');
  update public.payments set status = 'EXPIRED' where purpose = 'MERCH' and ref_id = o.id and status = 'CREATED';
end $$;

create or replace function public.api_my_orders() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare uid uuid := public.require_auth();
begin
  return (select coalesce(jsonb_agg(to_jsonb(t) order by t.id desc), '[]'::jsonb) from (
    select o.id, o.status, o.total_paise, o.price_tier, o.expires_at, o.picked_up_at, o.created_at,
           (select p.id from public.payments p where p.purpose = 'MERCH' and p.ref_id = o.id order by p.created_at desc limit 1) as payment_id,
           (select jsonb_agg(jsonb_build_object('name', pr.name, 'size', v.size, 'qty', i.qty, 'unit', i.unit_price_paise) order by i.id)
              from public.merch_order_items i join public.variants v on v.id = i.variant_id join public.products pr on pr.id = v.product_id
             where i.order_id = o.id) as items
      from public.merch_orders o where o.user_id = uid) t);
end $$;

create or replace function public.api_my_payments() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare uid uuid := public.require_auth();
begin
  return (select coalesce(jsonb_agg(to_jsonb(t) order by t.created_at desc), '[]'::jsonb) from (
    select p.id, p.purpose, p.amount_paise, p.status, p.fulfillment, p.created_at from public.payments p where p.user_id = uid) t);
end $$;

-- ---- public comms ----------------------------------------------------------------------
create or replace function public.api_announcements_list(p_limit int default 20) returns jsonb
language sql stable security definer set search_path = public as $$
  select coalesce(jsonb_agg(to_jsonb(t) order by t.published_at desc), '[]'::jsonb) from (
    select a.id, a.title, a.body, a.published_at, p.full_name as author
      from public.announcements a join public.profiles p on p.id = a.author_id
     where a.status = 'PUBLISHED' order by a.published_at desc limit greatest(p_limit, 1)) t
$$;

create or replace function public.api_announcement_get(p_id bigint) returns jsonb
language sql stable security definer set search_path = public as $$
  select to_jsonb(t) from (
    select a.id, a.title, a.body, a.published_at, p.full_name as author
      from public.announcements a join public.profiles p on p.id = a.author_id
     where a.id = p_id and a.status = 'PUBLISHED') t
$$;

create or replace function public.api_subscribe(p_email text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare em text := lower(trim(p_email)); s public.subscribers;
begin
  if em !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' or length(em) > 200 then perform public.fail('VALIDATION', 'Enter a valid email address'); end if;
  insert into public.subscribers (email, user_id) values (em, auth.uid())
  on conflict (lower(email)) do update set status = 'SUBSCRIBED', unsubscribed_at = null
  returning * into s;
  return jsonb_build_object('ok', true);
end $$;

create or replace function public.api_unsubscribe(p_token text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare s public.subscribers;
begin
  update public.subscribers set status = 'UNSUBSCRIBED', unsubscribed_at = public.app_now()
   where unsub_token = p_token returning * into s;
  if s.id is null then perform public.fail('NOT_FOUND', 'That unsubscribe link is not valid'); end if;
  return jsonb_build_object('ok', true, 'email', s.email);
end $$;

-- ---- member expenses --------------------------------------------------------------------
create or replace function public.api_expense_submit(p_category text, p_amount bigint, p_desc text, p_event bigint default null,
                                                    p_fundraiser bigint default null, p_task bigint default null) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_auth(); x public.expenses;
begin
  if p_amount is null or p_amount <= 0 then perform public.fail('VALIDATION', 'Enter an amount greater than zero'); end if;
  if p_category !~ '^50[0-9]{2}$' or not exists (select 1 from public.accounts where code = p_category) then
    perform public.fail('VALIDATION', 'Choose an expense category');
  end if;
  if coalesce(trim(p_desc), '') = '' then perform public.fail('VALIDATION', 'Describe what the expense was for'); end if;
  if p_task is not null and not exists (select 1 from public.tasks where id = p_task and fundraiser_id = p_fundraiser) then
    perform public.fail('VALIDATION', 'That task does not belong to the selected fundraiser');
  end if;
  insert into public.expenses (submitter_id, term_id, category_code, amount_paise, description, event_id, fundraiser_id, task_id)
  values (uid, public.open_term_id(), p_category, p_amount, trim(p_desc), p_event, p_fundraiser, p_task) returning * into x;
  return jsonb_build_object('id', x.id);
end $$;

create or replace function public.api_expense_add_receipt(p_expense bigint, p_path text, p_name text, p_mime text, p_size int) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_auth(); x public.expenses; r public.receipts;
begin
  select * into x from public.expenses where id = p_expense and submitter_id = uid;
  if x.id is null then perform public.fail('NOT_FOUND', 'Expense not found'); end if;
  if x.status not in ('SUBMITTED','APPROVED') then perform public.fail('VALIDATION', 'This expense can no longer take receipts'); end if;
  if p_mime not in ('image/png','image/jpeg','application/pdf') or p_size < 1 or p_size > 5242880 then
    perform public.fail('UPLOAD_REJECTED', 'Upload a PNG, JPG or PDF under 5 MB');
  end if;
  insert into public.receipts (uploader_id, expense_id, storage_path, original_name, mime, size_bytes)
  values (uid, x.id, p_path, left(p_name, 200), p_mime, p_size) returning * into r;
  return jsonb_build_object('id', r.id);
end $$;

create or replace function public.api_my_expenses() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare uid uuid := public.require_auth();
begin
  return (select coalesce(jsonb_agg(to_jsonb(t) order by t.id desc), '[]'::jsonb) from (
    select x.id, x.amount_paise, x.description, x.status, x.decision_note, x.created_at, a.name as category,
           (select count(*) from public.receipts r where r.expense_id = x.id) as receipts
      from public.expenses x join public.accounts a on a.code = x.category_code where x.submitter_id = uid) t);
end $$;

create or replace function public.api_receipt_path(p_receipt bigint) returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare uid uuid := public.require_auth(); r public.receipts;
begin
  select * into r from public.receipts where id = p_receipt;
  if r.id is null or not (r.uploader_id = uid or public.has_role('treasurer')) then
    perform public.fail('NOT_FOUND', 'Receipt not found');
  end if;
  return jsonb_build_object('path', r.storage_path, 'name', r.original_name, 'mime', r.mime);
end $$;

create or replace function public.api_task_set_status(p_task bigint, p_status text) returns void
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_auth(); t public.tasks;
begin
  if p_status not in ('TODO','DOING','DONE','BLOCKED') then perform public.fail('VALIDATION', 'Unknown status'); end if;
  select * into t from public.tasks where id = p_task;
  if t.id is null then perform public.fail('NOT_FOUND', 'Task not found'); end if;
  if t.owner_id is distinct from uid and not public.has_role('comms') then
    perform public.fail('FORBIDDEN', 'Only the task owner or a coordinator can change this');
  end if;
  update public.tasks set status = p_status where id = p_task;
end $$;

create or replace function public.api_my_tasks() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare uid uuid := public.require_auth();
begin
  return (select coalesce(jsonb_agg(to_jsonb(t) order by t.due_on nulls last, t.id), '[]'::jsonb) from (
    select k.id, k.title, k.status, k.due_on, f.title as fundraiser, f.id as fundraiser_id
      from public.tasks k join public.fundraisers f on f.id = k.fundraiser_id where k.owner_id = uid) t);
end $$;

-- Counts only; safe for the public landing page.
create or replace function public.api_public_stats() returns jsonb
language sql stable security definer set search_path = public as $$
  select jsonb_build_object(
    'members', (select count(*) from public.memberships where status = 'ACTIVE' and expires_at > public.app_now()),
    'events', (select count(*) from public.events where status in ('ON_SALE','CLOSED')),
    'tickets', (select count(*) from public.tickets where status in ('ISSUED','USED')),
    'orders', (select count(*) from public.merch_orders where status in ('PAID','PICKED_UP')))
$$;
