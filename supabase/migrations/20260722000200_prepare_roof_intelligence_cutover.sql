-- Additive preparation for the disabled-by-default Supabase reporting path.
-- No PCS or PilotPoint runtime currently calls these fields or functions.

begin;

alter table public.roof_intelligence_jobs
  add column idempotency_key text,
  add column worker_id text,
  add column heartbeat_at timestamptz,
  add column lease_expires_at timestamptz,
  add column attempt_count integer not null default 0 check (attempt_count >= 0);

create unique index roof_intelligence_jobs_idempotency_key
  on public.roof_intelligence_jobs (idempotency_key)
  where idempotency_key is not null;

create index roof_intelligence_jobs_worker_lease_idx
  on public.roof_intelligence_jobs (status, lease_expires_at)
  where status in ('queued', 'running');

alter table public.roof_intelligence_reports
  add column last_revision_at timestamptz not null default now(),
  add column retention_expires_at timestamptz not null default (now() + interval '90 days'),
  add constraint roof_intelligence_reports_retention_order
    check (retention_expires_at >= last_revision_at);

create index roof_intelligence_reports_retention_idx
  on public.roof_intelligence_reports (retention_expires_at)
  where status = 'active';

alter table public.roof_intelligence_report_revisions
  add column edit_patch jsonb not null default '{}'::jsonb
    check (jsonb_typeof(edit_patch) = 'object');

create table public.roof_intelligence_property_overrides (
  id uuid primary key default gen_random_uuid(),
  property_id uuid not null
    references public.roof_intelligence_properties(id)
    on update cascade
    on delete restrict,
  field_name text not null check (field_name = 'roof_area_sqft'),
  numeric_value numeric(14,2) not null check (numeric_value >= 0),
  source_revision_id uuid not null
    references public.roof_intelligence_report_revisions(id)
    on update cascade
    on delete restrict,
  reason text not null check (char_length(btrim(reason)) >= 10),
  created_by uuid references auth.users(id) on delete set null,
  effective_at timestamptz not null default now(),
  revoked_at timestamptz,
  revoked_by uuid references auth.users(id) on delete set null,
  revocation_reason text,
  created_at timestamptz not null default now(),
  check (revoked_at is null or revoked_at >= effective_at),
  check (
    (revoked_at is null and revoked_by is null and revocation_reason is null)
    or (
      revoked_at is not null
      and revoked_by is not null
      and char_length(btrim(revocation_reason)) >= 10
    )
  )
);

create unique index roof_intelligence_property_overrides_active_key
  on public.roof_intelligence_property_overrides (property_id, field_name)
  where revoked_at is null;

create index roof_intelligence_property_overrides_history_idx
  on public.roof_intelligence_property_overrides
    (property_id, field_name, effective_at desc);

create or replace function public.validate_roof_intelligence_property_override()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  revision_property_id uuid;
  revision_status text;
begin
  select report.property_id, revision.generation_status
    into revision_property_id, revision_status
    from public.roof_intelligence_report_revisions revision
    join public.roof_intelligence_reports report on report.id = revision.report_id
    where revision.id = new.source_revision_id;

  if revision_property_id is null then
    raise exception 'The source report revision does not exist';
  end if;
  if revision_property_id <> new.property_id then
    raise exception 'The square-footage override revision belongs to another property';
  end if;
  if revision_status <> 'ready' then
    raise exception 'A square-footage override requires a Ready source revision';
  end if;
  return new;
end;
$$;

create trigger roof_intelligence_property_overrides_validate
before insert or update of property_id, source_revision_id
on public.roof_intelligence_property_overrides
for each row execute function public.validate_roof_intelligence_property_override();

create or replace function public.extend_roof_intelligence_report_retention()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  update public.roof_intelligence_reports
  set last_revision_at = greatest(last_revision_at, new.created_at),
      retention_expires_at = greatest(
        retention_expires_at,
        new.created_at + interval '90 days'
      )
  where id = new.report_id;
  return new;
end;
$$;

create trigger roof_intelligence_report_revisions_extend_retention
after insert on public.roof_intelligence_report_revisions
for each row execute function public.extend_roof_intelligence_report_retention();

create or replace function public.claim_roof_intelligence_job(
  worker_name text,
  lease_seconds integer default 900
)
returns setof public.roof_intelligence_jobs
language plpgsql
security definer
set search_path = public
as $$
declare
  claimed_job_id uuid;
begin
  if char_length(btrim(worker_name)) = 0 then
    raise exception 'worker_name is required';
  end if;
  if lease_seconds < 30 or lease_seconds > 3600 then
    raise exception 'lease_seconds must be between 30 and 3600';
  end if;

  select id
    into claimed_job_id
    from public.roof_intelligence_jobs
    where status = 'queued'
       or (status = 'running' and lease_expires_at < now())
    order by queued_at, created_at
    for update skip locked
    limit 1;

  if claimed_job_id is null then
    return;
  end if;

  update public.roof_intelligence_jobs
  set status = 'running',
      stage = case when status = 'queued' then 'claimed' else 'reclaimed' end,
      worker_id = btrim(worker_name),
      started_at = coalesce(started_at, now()),
      heartbeat_at = now(),
      lease_expires_at = now() + make_interval(secs => lease_seconds),
      attempt_count = attempt_count + 1
  where id = claimed_job_id;

  return query
    select * from public.roof_intelligence_jobs where id = claimed_job_id;
end;
$$;

revoke all on function public.claim_roof_intelligence_job(text, integer)
  from public, anon, authenticated;
grant execute on function public.claim_roof_intelligence_job(text, integer)
  to service_role;

alter table public.roof_intelligence_property_overrides enable row level security;

comment on table public.roof_intelligence_property_overrides is
  'Explicit property-level square-footage corrections selected for future reports. Other manual report edits never carry forward.';
comment on column public.roof_intelligence_reports.retention_expires_at is
  'Report and all revisions remain available until 90 days after the latest revision.';
comment on column public.roof_intelligence_report_revisions.edit_patch is
  'Exact user-supplied fields for this revision; empty for fresh Revision 1 reports.';
comment on function public.claim_roof_intelligence_job(text, integer) is
  'Service-role-only atomic worker claim with a bounded lease. No current application calls this function.';

commit;
