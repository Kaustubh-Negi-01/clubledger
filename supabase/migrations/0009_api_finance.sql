-- Finance reports, integrity checks, term close, adjustments, handover, dashboards.

create or replace function public.api_finance_summary() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare t public.terms; res jsonb;
begin
  perform public.require_any_role(array['treasurer']);
  select * into t from public.terms where status = 'OPEN';
  select jsonb_build_object(
    'term', jsonb_build_object('id', t.id, 'label', t.label, 'starts_at', t.starts_at),
    'cash', jsonb_build_object(
      'cash_on_hand', public.account_balance('1000'),
      'in_clearing', public.account_balance('1100'),
      'unfulfilled', public.account_balance('2000'),
      'reimbursements_payable', public.account_balance('2100')),
    'income', (select coalesce(jsonb_agg(jsonb_build_object('code', a.code, 'name', a.name, 'amount', public.account_movement(a.code, t.id)) order by a.code), '[]'::jsonb)
                 from public.accounts a where a.type = 'INCOME'),
    'expenses', (select coalesce(jsonb_agg(jsonb_build_object('code', a.code, 'name', a.name, 'amount', public.account_movement(a.code, t.id)) order by a.code), '[]'::jsonb)
                 from public.accounts a where a.type = 'EXPENSE'),
    'adjustments', (select coalesce(jsonb_agg(jsonb_build_object('id', e.id, 'memo', e.memo, 'adjusts_term_id', e.adjusts_term_id)), '[]'::jsonb)
                 from public.journal_entries e where e.term_id = t.id and e.source_type = 'adjustment')
  ) into res;
  return res;
end $$;

create or replace function public.api_ledger(p_account text default null, p_limit int default 100) returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.require_role('treasurer');
  return (select coalesce(jsonb_agg(to_jsonb(t) order by t.id desc), '[]'::jsonb) from (
    select e.id, e.entry_date, e.source_type, e.source_id, e.source_event, e.memo, e.term_id, e.reverses_entry_id, e.adjusts_term_id,
           (select coalesce(jsonb_agg(jsonb_build_object('account', l.account_code, 'name', a.name, 'debit', l.debit, 'credit', l.credit) order by l.id), '[]'::jsonb)
              from public.journal_lines l join public.accounts a on a.code = l.account_code where l.entry_id = e.id) as lines
      from public.journal_entries e
     where e.status = 'POSTED'
       and (p_account is null or exists (select 1 from public.journal_lines l where l.entry_id = e.id and l.account_code = p_account))
     order by e.id desc limit greatest(p_limit, 1)) t);
end $$;

create or replace function public.api_integrity() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare checks jsonb := '[]'::jsonb; d bigint; c bigint; n int;
begin
  perform public.require_role('treasurer');
  select coalesce(sum(debit), 0), coalesce(sum(credit), 0) into d, c
    from public.journal_lines l join public.journal_entries e on e.id = l.entry_id and e.status = 'POSTED';
  checks := checks || jsonb_build_object('name', 'Total debits equal total credits', 'ok', d = c, 'detail', d || ' / ' || c);

  select count(*) into n from public.payments p
   where p.status in ('SUCCEEDED','REFUNDED')
     and (select count(*) from public.journal_entries e where e.source_type = 'payment' and e.source_id = p.id::text and e.source_event = 'received') <> 1;
  checks := checks || jsonb_build_object('name', 'Every received payment has exactly one ledger entry', 'ok', n = 0, 'detail', n || ' exceptions');

  select count(*) into n from public.expenses x
   where x.status = 'PAID' and (select count(*) from public.journal_entries e where e.source_type = 'expense' and e.source_id = x.id::text) <> 2;
  checks := checks || jsonb_build_object('name', 'Every paid expense was approved and paid in the ledger', 'ok', n = 0, 'detail', n || ' exceptions');

  select count(*) into n from (
    select p.id from public.payments p
     where p.purpose = 'TICKET' and p.status = 'SUCCEEDED' and p.fulfillment = 'FULFILLED'
       and coalesce((select sum(l.credit - l.debit) from public.journal_lines l join public.journal_entries e on e.id = l.entry_id
                      where e.source_type = 'payment' and e.source_id = p.id::text and l.account_code = '4100'), 0)
        <> coalesce((select sum(t.price_paise) from public.tickets t where t.payment_id = p.id and t.status in ('ISSUED','USED')), 0)) x;
  checks := checks || jsonb_build_object('name', 'Ticket income in the ledger matches ticket prices per payment', 'ok', n = 0, 'detail', n || ' exceptions');

  select count(*) into n from public.variants v
   where v.reserved_qty <> coalesce((select sum(i.qty) from public.merch_order_items i join public.merch_orders o on o.id = i.order_id
                                       where i.variant_id = v.id and o.status in ('RESERVED','PAID')), 0);
  checks := checks || jsonb_build_object('name', 'Reserved stock matches open orders', 'ok', n = 0, 'detail', n || ' exceptions');

  select count(*) into n from public.events e
   where (select count(*) from public.tickets t where t.event_id = e.id and t.status in ('ISSUED','USED')) > e.capacity;
  checks := checks || jsonb_build_object('name', 'No event is oversold', 'ok', n = 0, 'detail', n || ' exceptions');
  return checks;
end $$;

-- ---- close ------------------------------------------------------------------------------------
create or replace function public.close_checks() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare checks jsonb := '[]'::jsonb; n int; t public.terms;
begin
  select * into t from public.terms where status = 'OPEN';
  select count(*) into n from public.payments where status = 'CREATED';
  checks := checks || jsonb_build_object('code', 'PAYMENTS_OPEN', 'label', 'No payments waiting on the gateway', 'ok', n = 0, 'detail', n || ' open');
  select count(*) into n from public.payments where status = 'SUCCEEDED' and fulfillment = 'UNFULFILLED';
  checks := checks || jsonb_build_object('code', 'UNFULFILLED', 'label', 'No unfulfilled payments left to resolve', 'ok', n = 0, 'detail', n || ' to resolve');
  select count(*) into n from public.expenses where status in ('SUBMITTED','APPROVED');
  checks := checks || jsonb_build_object('code', 'EXPENSES_OPEN', 'label', 'Every expense is paid, rejected or voided', 'ok', n = 0, 'detail', n || ' open');
  select (select count(*) from public.ticket_holds where status = 'HELD' and expires_at > public.app_now())
       + (select count(*) from public.merch_orders where status = 'RESERVED' and expires_at > public.app_now()) into n;
  checks := checks || jsonb_build_object('code', 'RESERVATIONS', 'label', 'No live ticket holds or merchandise reservations', 'ok', n = 0, 'detail', n || ' live');
  n := (public.account_balance('2000') <> 0)::int + (public.account_balance('2100') <> 0)::int;
  checks := checks || jsonb_build_object('code', 'LIABILITIES', 'label', 'Obligations and reimbursements payable are zero', 'ok', n = 0,
            'detail', 'obligations ' || public.account_balance('2000') || ', payable ' || public.account_balance('2100'));
  checks := checks || jsonb_build_object('code', 'CLEARING', 'label', 'All received money has been paid out to the bank', 'ok', public.account_balance('1100') = 0,
            'detail', 'clearing ' || public.account_balance('1100'));
  select count(*) into n from public.expenses x where x.status = 'PAID' and not exists (select 1 from public.receipts r where r.expense_id = x.id);
  checks := checks || jsonb_build_object('code', 'RECEIPTS', 'label', 'Every paid expense has a receipt', 'ok', n = 0, 'detail', n || ' missing');
  checks := checks || jsonb_build_object('code', 'TERM_AGE', 'label', 'The term has started', 'ok', public.app_now() > t.starts_at, 'detail', '');
  return checks;
end $$;

create or replace function public.api_close_status() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare t public.terms;
begin
  perform public.require_role('treasurer');
  select * into t from public.terms where status = 'OPEN';
  return jsonb_build_object('term', jsonb_build_object('id', t.id, 'label', t.label, 'starts_at', t.starts_at),
    'checks', public.close_checks(),
    'snapshots', (select coalesce(jsonb_agg(jsonb_build_object('term_id', s.term_id, 'label', tt.label, 'taken_at', s.taken_at, 'sha', s.content_sha256,
                    'totals', s.totals) order by s.id desc), '[]'::jsonb)
                    from public.close_snapshots s join public.terms tt on tt.id = s.term_id));
end $$;

create or replace function public.api_close_term() returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('treasurer'); t public.terms; chk jsonb; failed text; wm bigint; prev_wm bigint;
        bal jsonb := '{}'::jsonb; a record; opening bigint; mv bigint; totals jsonb; now_ts timestamptz := public.app_now(); nt public.terms;
begin
  select * into t from public.terms where status = 'OPEN' for update;
  chk := public.close_checks();
  select string_agg(x ->> 'label', '; ') into failed from jsonb_array_elements(chk) x where (x ->> 'ok')::boolean is not true;
  if failed is not null then perform public.fail('CLOSE_BLOCKED', 'Cannot close yet: ' || failed); end if;

  select coalesce(max(id), 0) into wm from public.journal_entries;
  select coalesce(max(watermark_entry_id), 0) into prev_wm from public.close_snapshots;
  for a in select code, name, type from public.accounts order by code loop
    if a.type in ('ASSET','LIABILITY') then
      opening := public.account_balance(a.code, prev_wm);
      mv := public.account_movement(a.code, t.id);
      if opening + mv <> public.account_balance(a.code, wm) then
        raise exception 'INTERNAL|opening + movement does not equal closing for account %', a.code;
      end if;
      bal := bal || jsonb_build_object(a.code, jsonb_build_object('name', a.name, 'opening', opening, 'movement', mv, 'closing', opening + mv));
    else
      bal := bal || jsonb_build_object(a.code, jsonb_build_object('name', a.name, 'opening', 0, 'movement', public.account_movement(a.code, t.id),
                                                                 'closing', public.account_movement(a.code, t.id)));
    end if;
  end loop;
  totals := jsonb_build_object('term', t.label, 'watermark', wm, 'accounts', bal,
    'counts', jsonb_build_object(
      'tickets_sold', (select count(*) from public.tickets where status in ('ISSUED','USED')),
      'tickets_used', (select count(*) from public.tickets where status = 'USED'),
      'active_members', (select count(*) from public.memberships where status = 'ACTIVE'),
      'orders_paid', (select count(*) from public.merch_orders where status in ('PAID','PICKED_UP'))));
  insert into public.close_snapshots (term_id, taken_by, watermark_entry_id, totals, content_sha256, taken_at)
  values (t.id, uid, wm, totals, encode(sha256(convert_to(totals::text, 'UTF8')), 'hex'), now_ts);

  update public.terms set status = 'CLOSED', ends_at = now_ts, closed_at = now_ts where id = t.id;
  insert into public.terms (label, starts_at, status)
  values ('Term ' || ((select count(*) from public.terms) + 1), now_ts, 'OPEN') returning * into nt;
  insert into public.audit_log (actor, action, entity, entity_id) values (uid, 'term.close', 'term', t.id::text);
  return jsonb_build_object('closed', t.label, 'opened', nt.label, 'watermark', wm);
end $$;

create or replace function public.api_adjustment(p_adjusts bigint, p_memo text, p_lines jsonb) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('treasurer'); eid bigint;
begin
  if coalesce(trim(p_memo), '') = '' then perform public.fail('VALIDATION', 'A memo is required for adjustments'); end if;
  eid := public.post_entry('adjustment', gen_random_uuid()::text, 'adjustment', trim(p_memo), p_lines, null, p_adjusts);
  return jsonb_build_object('id', eid);
end $$;

create or replace function public.api_handover(p_to uuid, p_roles text[], p_notes text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare uid uuid := public.require_role('admin'); t public.terms; r text; changes jsonb := '[]'::jsonb;
begin
  select * into t from public.terms where status = 'CLOSED' order by id desc limit 1;
  if t.id is null or not exists (select 1 from public.close_snapshots where term_id = t.id) then
    perform public.fail('VALIDATION', 'Close a term before handing over');
  end if;
  if exists (select 1 from public.officer_handover where term_id = t.id) then
    perform public.fail('VALIDATION', 'The handover for ' || t.label || ' is already done');
  end if;
  if p_to = uid then perform public.fail('VALIDATION', 'Choose someone else to hand over to'); end if;
  foreach r in array p_roles loop
    if r not in ('admin','treasurer','organizer','door','store','comms') then perform public.fail('VALIDATION', 'Unknown role ' || r); end if;
    insert into public.user_roles (user_id, role) values (p_to, r) on conflict do nothing;
    update public.user_roles set revoked_at = public.app_now() where user_id = uid and role = r and revoked_at is null;
    changes := changes || jsonb_build_object('role', r, 'from', uid, 'to', p_to);
  end loop;
  insert into public.officer_handover (term_id, from_user, to_user, notes, role_changes) values (t.id, uid, p_to, p_notes, changes);
  return jsonb_build_object('term', t.label, 'roles', changes);
end $$;

create or replace function public.api_people() returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.require_any_role(array['comms','organizer','treasurer','admin']);
  return (select coalesce(jsonb_agg(jsonb_build_object('id', p.id, 'name', p.full_name, 'email', p.email) order by p.full_name), '[]'::jsonb) from public.profiles p);
end $$;

create or replace function public.api_admin_overview() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare uid uuid := public.require_auth(); t public.terms; fin boolean := public.has_role('treasurer');
begin
  if not (public.has_role('organizer') or public.has_role('door') or public.has_role('store') or public.has_role('comms') or fin) then
    perform public.fail('FORBIDDEN', 'You do not have permission to do that');
  end if;
  select * into t from public.terms where status = 'OPEN';
  return jsonb_build_object(
    'term', t.label,
    'active_members', (select count(*) from public.memberships where status = 'ACTIVE' and expires_at > public.app_now()),
    'tickets_sold', (select count(*) from public.tickets where status in ('ISSUED','USED')),
    'checked_in', (select count(*) from public.tickets where status = 'USED'),
    'low_stock', (select count(*) from public.variants where physical_qty - reserved_qty <= 3),
    'orders_to_hand_over', (select count(*) from public.merch_orders where status = 'PAID'),
    'queued_mail', (select count(*) from public.mail_outbox where status = 'QUEUED'),
    'open_tasks', (select count(*) from public.tasks where status <> 'DONE'),
    'expenses_waiting', case when fin then (select count(*) from public.expenses where status = 'SUBMITTED') else null end,
    'unfulfilled', case when fin then (select count(*) from public.payments where status = 'SUCCEEDED' and fulfillment = 'UNFULFILLED') else null end,
    'income', case when fin then (select coalesce(sum(public.account_movement(a.code, t.id)), 0) from public.accounts a where a.type = 'INCOME') else null end,
    'spent', case when fin then (select coalesce(sum(public.account_movement(a.code, t.id)), 0) from public.accounts a where a.type = 'EXPENSE') else null end,
    'cash', case when fin then public.account_balance('1000') else null end,
    'upcoming', (select coalesce(jsonb_agg(to_jsonb(e)), '[]'::jsonb) from (
        select id, title, starts_at, sold, capacity from (
          select ev.id, ev.title, ev.starts_at, ev.capacity,
                 (select count(*) from public.tickets x where x.event_id = ev.id and x.status in ('ISSUED','USED')) as sold
            from public.events ev where ev.status = 'ON_SALE' and ev.ends_at > public.app_now() order by ev.starts_at limit 4) z) e));
end $$;

create or replace function public.api_member_home() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare uid uuid := public.require_auth();
begin
  return jsonb_build_object(
    'open_payments', (select coalesce(jsonb_agg(jsonb_build_object('id', p.id, 'purpose', p.purpose, 'amount_paise', p.amount_paise, 'created_at', p.created_at)), '[]'::jsonb)
                        from public.payments p where p.user_id = uid and p.status = 'CREATED'),
    'upcoming_tickets', (select count(*) from public.tickets t join public.events e on e.id = t.event_id
                          where t.user_id = uid and t.status = 'ISSUED' and e.ends_at > public.app_now()),
    'orders_open', (select count(*) from public.merch_orders where user_id = uid and status in ('RESERVED','PAID')),
    'tasks_open', (select count(*) from public.tasks where owner_id = uid and status <> 'DONE'));
end $$;
