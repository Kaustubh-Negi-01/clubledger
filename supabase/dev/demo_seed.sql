-- Demo data for the no-credentials preview. Never applied to a real Supabase project.
-- Everything goes through the same api_* functions the app uses, so the books are consistent.

insert into auth.users (id, email, raw_user_meta_data) values
  ('00000000-0000-4000-8000-000000000001', 'priya@skyline.test', '{"full_name":"Priya Nair"}'),
  ('00000000-0000-4000-8000-000000000002', 'rohan@skyline.test', '{"full_name":"Rohan Kapoor"}'),
  ('00000000-0000-4000-8000-000000000003', 'ishaan@skyline.test', '{"full_name":"Ishaan Verma"}'),
  ('00000000-0000-4000-8000-000000000004', 'maya@skyline.test', '{"full_name":"Maya Fernandes"}'),
  ('00000000-0000-4000-8000-000000000005', 'dev@skyline.test', '{"full_name":"Dev Malhotra"}'),
  ('00000000-0000-4000-8000-000000000011', 'aanya@skyline.test', '{"full_name":"Aanya Iyer"}'),
  ('00000000-0000-4000-8000-000000000012', 'kabir@skyline.test', '{"full_name":"Kabir Singh"}'),
  ('00000000-0000-4000-8000-000000000013', 'meera@skyline.test', '{"full_name":"Meera Joshi"}'),
  ('00000000-0000-4000-8000-000000000014', 'neil@skyline.test', '{"full_name":"Neil D''Souza"}'),
  ('00000000-0000-4000-8000-000000000015', 'tara@skyline.test', '{"full_name":"Tara Bose"}'),
  ('00000000-0000-4000-8000-000000000016', 'vikram@skyline.test', '{"full_name":"Vikram Rao"}'),
  ('00000000-0000-4000-8000-000000000017', 'sana@skyline.test', '{"full_name":"Sana Qureshi"}'),
  ('00000000-0000-4000-8000-000000000018', 'arjun@skyline.test', '{"full_name":"Arjun Pillai"}');

insert into public.user_roles (user_id, role) values
  ('00000000-0000-4000-8000-000000000001', 'organizer'),
  ('00000000-0000-4000-8000-000000000001', 'comms'),
  ('00000000-0000-4000-8000-000000000002', 'treasurer'),
  ('00000000-0000-4000-8000-000000000003', 'door'),
  ('00000000-0000-4000-8000-000000000003', 'store');

update public.terms set starts_at = now() - interval '40 days' where status = 'OPEN';

do $$
declare
  priya uuid := '00000000-0000-4000-8000-000000000001';
  rohan uuid := '00000000-0000-4000-8000-000000000002';
  ishaan uuid := '00000000-0000-4000-8000-000000000003';
  maya uuid := '00000000-0000-4000-8000-000000000004';
  dev uuid := '00000000-0000-4000-8000-000000000005';
  m uuid; j jsonb; h jsonb; ev jsonb; kickoff jsonb; gala jsonb; mic jsonb; cleanup jsonb; pr jsonb; t jsonb; fr jsonb; vs jsonb;
  names uuid[] := array[maya, '00000000-0000-4000-8000-000000000011', '00000000-0000-4000-8000-000000000012',
    '00000000-0000-4000-8000-000000000013', '00000000-0000-4000-8000-000000000014', '00000000-0000-4000-8000-000000000015',
    '00000000-0000-4000-8000-000000000016', '00000000-0000-4000-8000-000000000017', '00000000-0000-4000-8000-000000000018'];
  i int; tix jsonb;
begin
  -- the past: members join, a kickoff event happens, books are settled
  perform set_config('app.now_override', (now() - interval '30 days')::text, false);
  foreach m in array names loop
    perform set_config('request.jwt.claim.sub', m::text, false);
    j := public.api_join(1);
    perform public.api_pay_simulate((j ->> 'payment_id')::uuid, 'success');
  end loop;

  perform set_config('request.jwt.claim.sub', priya::text, false);
  perform set_config('app.now_override', (now() - interval '8 days')::text, false);
  kickoff := public.api_event_save(null, 'Hack Night Kickoff', 'Teams form, pizza arrives, the first commit lands before midnight.',
    'Skyline Innovation Lab', now() - interval '6 days', now() - interval '6 days' + interval '4 hours', 60, 0, 20000, 4, '');
  perform public.api_event_set_status((kickoff ->> 'id')::bigint, 'ON_SALE');
  for i in 1 .. 6 loop
    perform set_config('request.jwt.claim.sub', names[i]::text, false);
    h := public.api_hold_tickets((kickoff ->> 'id')::bigint, 1 + (i % 2));
    if (h ->> 'payment_id') is not null then perform public.api_pay_simulate((h ->> 'payment_id')::uuid, 'success'); end if;
  end loop;
  perform set_config('request.jwt.claim.sub', dev::text, false);
  h := public.api_hold_tickets((kickoff ->> 'id')::bigint, 2);
  perform public.api_pay_simulate((h ->> 'payment_id')::uuid, 'success');
  perform set_config('app.now_override', (now() - interval '6 days' + interval '30 minutes')::text, false);
  perform set_config('request.jwt.claim.sub', ishaan::text, false);
  for tix in select to_jsonb(x) from (select code from public.tickets where event_id = (kickoff ->> 'id')::bigint order by id limit 7) x loop
    perform public.api_checkin((kickoff ->> 'id')::bigint, tix ->> 'code');
  end loop;
  perform set_config('app.now_override', (now() - interval '5 days')::text, false);
  perform set_config('request.jwt.claim.sub', priya::text, false);
  perform public.api_event_set_status((kickoff ->> 'id')::bigint, 'CLOSED');
  perform set_config('request.jwt.claim.sub', rohan::text, false);
  perform public.api_settle();

  -- the present
  perform set_config('app.now_override', '', false);
  perform set_config('request.jwt.claim.sub', priya::text, false);
  gala := public.api_event_save(null, 'Spring Gala', E'The club''s biggest night: a three-course dinner, a live band and the annual awards. Dress up, bring friends, stay for the sunrise playlist.',
    'Skyline Grand Hall', now() + interval '18 days', now() + interval '18 days' + interval '5 hours', 120, 65000, 95000, 4, '');
  mic := public.api_event_save(null, 'Open Mic Night', 'Poetry, stand-up, acoustic sets. Sign up at the door or just come to listen.',
    'The Annex Cafe', now() + interval '6 days', now() + interval '6 days' + interval '3 hours', 60, 0, 15000, 4, '');
  cleanup := public.api_event_save(null, 'Campus Cleanup Drive', 'Gloves and bags provided. Two hours, one lake, a very smug feeling afterwards.',
    'North Lake Gate', now() + interval '10 days', now() + interval '10 days' + interval '2 hours', 80, 0, 0, 6, '');
  perform public.api_event_set_status((gala ->> 'id')::bigint, 'ON_SALE');
  perform public.api_event_set_status((mic ->> 'id')::bigint, 'ON_SALE');
  perform public.api_event_set_status((cleanup ->> 'id')::bigint, 'ON_SALE');
  for i in 2 .. 5 loop
    perform set_config('request.jwt.claim.sub', names[i]::text, false);
    h := public.api_hold_tickets((gala ->> 'id')::bigint, 2);
    perform public.api_pay_simulate((h ->> 'payment_id')::uuid, 'success');
  end loop;
  perform set_config('request.jwt.claim.sub', names[7]::text, false);
  perform public.api_hold_tickets((mic ->> 'id')::bigint, 2);

  -- store
  perform set_config('request.jwt.claim.sub', ishaan::text, false);
  pr := public.api_product_save(null, 'Skyline Hoodie', 'Heavyweight 400gsm fleece with the embroidered skyline crest. Runs true to size.', 149900, '', true);
  perform public.api_variant_set_stock((pr ->> 'id')::bigint, 'S', 12);
  perform public.api_variant_set_stock((pr ->> 'id')::bigint, 'M', 18);
  perform public.api_variant_set_stock((pr ->> 'id')::bigint, 'L', 14);
  perform public.api_variant_set_stock((pr ->> 'id')::bigint, 'XL', 2);
  pr := public.api_product_save(null, 'Crest T-Shirt', 'Soft combed cotton, screen-printed crest on the chest.', 69900, '', true);
  perform public.api_variant_set_stock((pr ->> 'id')::bigint, 'S', 20);
  perform public.api_variant_set_stock((pr ->> 'id')::bigint, 'M', 25);
  perform public.api_variant_set_stock((pr ->> 'id')::bigint, 'L', 25);
  pr := public.api_product_save(null, 'Canvas Tote', 'Heavy canvas, fits a laptop and a week of lecture notes.', 34900, '', true);
  perform public.api_variant_set_stock((pr ->> 'id')::bigint, 'One size', 40);
  perform set_config('request.jwt.claim.sub', names[3]::text, false);
  vs := (select jsonb_agg(jsonb_build_object('variant_id', v.id, 'qty', 1)) from public.variants v where v.sku in ('SKU-1-M', 'SKU-2-L'));
  j := public.api_reserve_cart(vs);
  perform public.api_pay_simulate((j ->> 'payment_id')::uuid, 'success');

  -- announcements and subscribers
  perform public.api_subscribe('maya@skyline.test'); perform public.api_subscribe('aanya@skyline.test');
  perform public.api_subscribe('kabir@skyline.test'); perform public.api_subscribe('alumni@skyline.test');
  perform set_config('request.jwt.claim.sub', priya::text, false);
  perform public.api_announcement_save(null, 'Spring Gala tickets are on sale', E'Member tickets are 35% off the public price. Seats are limited to 120, so grab yours early. Bring a plus-one: you can buy up to four tickets per order.', true);
  perform public.api_announcement_save(null, 'General body meeting, Thursday 6 pm', E'We are voting on the semester budget and the Open Mic format. Pizza after. Everyone is welcome, members vote.', true);
  perform public.api_announcement_save(null, 'Bake sale volunteers needed', E'We need bakers, a table crew and two people on the cash box. Pick a task on the Fundraisers page.', false);
  perform public.api_outbox_process(100);

  -- fundraiser
  fr := public.api_fundraiser_save(null, 'Monsoon Bake Sale', 'Brownies, cookies and chai outside the library. All proceeds fund the Spring Gala band.', 1500000, 'ACTIVE');
  perform public.api_task_save(null, (fr ->> 'id')::bigint, 'Buy ingredients', names[2], (now() at time zone 'Asia/Kolkata')::date - 2, 'DONE');
  perform public.api_task_save(null, (fr ->> 'id')::bigint, 'Bake 60 brownies', names[3], (now() at time zone 'Asia/Kolkata')::date + 2, 'DOING');
  perform public.api_task_save(null, (fr ->> 'id')::bigint, 'Table, signage and cash box', names[4], (now() at time zone 'Asia/Kolkata')::date + 4, 'TODO');
  perform public.api_task_save(null, (fr ->> 'id')::bigint, 'Social posts and posters', priya, (now() at time zone 'Asia/Kolkata')::date - 1, 'BLOCKED');

  perform set_config('request.jwt.claim.sub', names[2]::text, false);
  perform public.api_expense_submit('5020', 230000, 'Flour, butter, cocoa and chai for the bake sale', null, (fr ->> 'id')::bigint, null);
  perform set_config('request.jwt.claim.sub', names[3]::text, false);
  perform public.api_expense_submit('5000', 480000, 'Open Mic sound equipment hire', (mic ->> 'id')::bigint, null, null);

  perform set_config('request.jwt.claim.sub', '', false);
end $$;
