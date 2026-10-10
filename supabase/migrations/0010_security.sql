-- Lock the Data API: tables are private (RLS on, no policies, no grants). The app talks to the
-- database only through api_* functions, which authorize every call themselves.
-- Convention for future migrations: public functions must be named api_*; everything else is internal.

do $$
declare t record; f record;
begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t.tablename);
    execute format('revoke all on public.%I from anon, authenticated', t.tablename);
  end loop;
  execute 'revoke all on all sequences in schema public from anon, authenticated';

  -- Supabase grants EXECUTE on new functions to anon/authenticated by default: take it all back, then grant the API.
  execute 'revoke execute on all functions in schema public from public, anon, authenticated';
  for f in select p.oid::regprocedure as sig, p.proname from pg_proc p
            join pg_namespace n on n.oid = p.pronamespace
           where n.nspname = 'public' and p.proname like 'api\_%' loop
    execute format('grant execute on function %s to anon, authenticated', f.sig);
  end loop;
end $$;

-- Maintenance may be triggered by the server cron with the service role only.
grant execute on function public.maintenance_run() to service_role;
grant usage on schema public to anon, authenticated, service_role;
