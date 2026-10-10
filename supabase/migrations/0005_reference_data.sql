-- Reference data required by every deployment (chart of accounts, first open term, default plan).

insert into public.accounts (code, name, type) values
  ('1000', 'Cash and bank', 'ASSET'),
  ('1100', 'Payment clearing (received, not yet paid out)', 'ASSET'),
  ('2000', 'Unfulfilled payments obligation', 'LIABILITY'),
  ('2100', 'Reimbursements payable', 'LIABILITY'),
  ('4000', 'Membership dues income', 'INCOME'),
  ('4100', 'Ticket income', 'INCOME'),
  ('4200', 'Merchandise income', 'INCOME'),
  ('5000', 'Events expenses', 'EXPENSE'),
  ('5010', 'Merchandise stock expenses', 'EXPENSE'),
  ('5020', 'Fundraiser expenses', 'EXPENSE'),
  ('5090', 'Other expenses', 'EXPENSE')
on conflict (code) do nothing;

insert into public.terms (label, starts_at, status)
select 'Founding term', date_trunc('day', now()) - interval '1 day', 'OPEN'
where not exists (select 1 from public.terms);

insert into public.membership_plans (code, name, dues_paise, ticket_discount_bps, merch_discount_bps, perks)
values ('MEMBER', 'Skyline Member', 50000, 2000, 1000,
        '["20% off every event ticket","10% off merchandise","Member-only announcements","Voting rights at the annual meeting"]'::jsonb)
on conflict (code) do nothing;
