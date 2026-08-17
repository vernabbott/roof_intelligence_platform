begin;

-- This is an internal event-trigger function installed by the hosted project.
-- Event-trigger execution does not require Data API clients to call it, so
-- remove the RPC surface inherited from PostgreSQL's default function grants.
revoke all on function public.rls_auto_enable() from public;
revoke all on function public.rls_auto_enable() from anon;
revoke all on function public.rls_auto_enable() from authenticated;

comment on function public.rls_auto_enable() is
  'Internal event-trigger helper; direct Data API execution is prohibited.';

commit;
