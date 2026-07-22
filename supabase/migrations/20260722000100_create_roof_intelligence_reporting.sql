-- Central Roof Intelligence persistence for PCS and PilotPoint IQ.
--
-- This migration creates empty production structures only. It intentionally
-- does not import local test jobs, reports, PDFs, imagery, health checks, or
-- analysis JSON, and it does not connect either application to Supabase.

begin;

create extension if not exists pgcrypto;

create table public.roof_intelligence_properties (
  id uuid primary key default gen_random_uuid(),
  canonical_key text not null unique check (btrim(canonical_key) <> ''),
  canonical_footprint_id bigint
    references public.canonical_building_footprints(id)
    on update cascade
    on delete set null,
  normalized_address text not null check (btrim(normalized_address) <> ''),
  address text,
  city text,
  state text check (state is null or char_length(btrim(state)) = 2),
  zip_code text,
  county text,
  parcel_number text,
  latitude double precision check (latitude is null or latitude between -90 and 90),
  longitude double precision check (longitude is null or longitude between -180 and 180),
  current_source_data jsonb not null default '{}'::jsonb
    check (jsonb_typeof(current_source_data) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index roof_intelligence_properties_parcel_idx
  on public.roof_intelligence_properties (state, county, parcel_number)
  where parcel_number is not null;

create index roof_intelligence_properties_address_idx
  on public.roof_intelligence_properties (normalized_address);

create index roof_intelligence_properties_footprint_idx
  on public.roof_intelligence_properties (canonical_footprint_id)
  where canonical_footprint_id is not null;

create table public.roof_intelligence_jobs (
  id uuid primary key default gen_random_uuid(),
  job_type text not null check (
    job_type in ('individual_address', 'area_selection', 'zip_batch')
  ),
  requested_by uuid references auth.users(id) on delete set null,
  status text not null default 'queued' check (
    status in (
      'queued', 'running', 'completed', 'completed_with_errors',
      'failed', 'cancelled'
    )
  ),
  stage text not null default 'queued' check (btrim(stage) <> ''),
  input jsonb not null default '{}'::jsonb check (jsonb_typeof(input) = 'object'),
  candidate_count integer not null default 0 check (candidate_count >= 0),
  completed_count integer not null default 0 check (completed_count >= 0),
  failed_count integer not null default 0 check (failed_count >= 0),
  skipped_count integer not null default 0 check (skipped_count >= 0),
  remaining_count integer not null default 0 check (remaining_count >= 0),
  error_code text,
  error_message text,
  error_details jsonb not null default '{}'::jsonb
    check (jsonb_typeof(error_details) = 'object'),
  retryable boolean not null default false,
  worker_version text,
  queued_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (started_at is null or started_at >= queued_at),
  check (finished_at is null or started_at is null or finished_at >= started_at)
);

create index roof_intelligence_jobs_status_idx
  on public.roof_intelligence_jobs (status, queued_at);

create index roof_intelligence_jobs_requester_idx
  on public.roof_intelligence_jobs (requested_by, created_at desc)
  where requested_by is not null;

create table public.roof_intelligence_job_items (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null
    references public.roof_intelligence_jobs(id)
    on update cascade
    on delete cascade,
  property_id uuid
    references public.roof_intelligence_properties(id)
    on update cascade
    on delete set null,
  candidate_key text,
  input jsonb not null default '{}'::jsonb check (jsonb_typeof(input) = 'object'),
  status text not null default 'pending' check (
    status in ('pending', 'running', 'completed', 'failed', 'skipped', 'cancelled')
  ),
  stage text not null default 'pending' check (btrim(stage) <> ''),
  reason_code text,
  message text,
  error_details jsonb not null default '{}'::jsonb
    check (jsonb_typeof(error_details) = 'object'),
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  unique (job_id, candidate_key),
  check (finished_at is null or started_at is null or finished_at >= started_at)
);

create index roof_intelligence_job_items_job_status_idx
  on public.roof_intelligence_job_items (job_id, status, created_at);

create index roof_intelligence_job_items_property_idx
  on public.roof_intelligence_job_items (property_id, created_at desc)
  where property_id is not null;

create table public.roof_intelligence_reports (
  id uuid primary key default gen_random_uuid(),
  property_id uuid not null
    references public.roof_intelligence_properties(id)
    on update cascade
    on delete restrict,
  source_job_id uuid
    references public.roof_intelligence_jobs(id)
    on update cascade
    on delete set null,
  source_job_item_id uuid
    references public.roof_intelligence_job_items(id)
    on update cascade
    on delete set null,
  created_by uuid references auth.users(id) on delete set null,
  status text not null default 'active' check (status in ('active', 'archived')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index roof_intelligence_reports_job_item_key
  on public.roof_intelligence_reports (source_job_item_id)
  where source_job_item_id is not null;

create index roof_intelligence_reports_property_idx
  on public.roof_intelligence_reports (property_id, created_at desc);

create index roof_intelligence_reports_job_idx
  on public.roof_intelligence_reports (source_job_id, created_at desc)
  where source_job_id is not null;

create table public.roof_intelligence_report_revisions (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null
    references public.roof_intelligence_reports(id)
    on update cascade
    on delete restrict,
  revision_number integer not null check (revision_number >= 1),
  parent_revision_id uuid
    references public.roof_intelligence_report_revisions(id)
    on update cascade
    on delete restrict,
  revision_kind text not null default 'initial' check (
    revision_kind in ('initial', 'manual_edit', 'source_refresh')
  ),
  generation_status text not null default 'draft' check (
    generation_status in ('draft', 'generating', 'ready', 'technical_failure')
  ),
  created_by uuid references auth.users(id) on delete set null,
  revision_note text,

  roof_area_sqft numeric(14,2) check (roof_area_sqft is null or roof_area_sqft >= 0),
  roof_squares numeric(14,2) check (roof_squares is null or roof_squares >= 0),
  roof_type text,
  roof_system text,
  roof_condition_score numeric(5,2) check (
    roof_condition_score is null or roof_condition_score between 0 and 100
  ),
  condition_label text,
  risk_level text,
  report_summary text,
  recommendation text,

  source_snapshot jsonb not null default '{}'::jsonb
    check (jsonb_typeof(source_snapshot) = 'object'),
  analysis_snapshot jsonb not null default '{}'::jsonb
    check (jsonb_typeof(analysis_snapshot) = 'object'),
  calculated_snapshot jsonb not null default '{}'::jsonb
    check (jsonb_typeof(calculated_snapshot) = 'object'),
  render_snapshot jsonb not null default '{}'::jsonb
    check (jsonb_typeof(render_snapshot) = 'object'),
  snapshot_schema_version integer not null default 1 check (snapshot_schema_version >= 1),
  workflow_version text,
  renderer_version text,
  calculation_version text,
  generated_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (report_id, revision_number),
  check (parent_revision_id is null or parent_revision_id <> id),
  check (generation_status <> 'ready' or generated_at is not null),
  check (
    (revision_number = 1 and parent_revision_id is null and revision_kind = 'initial')
    or (
      revision_number > 1
      and parent_revision_id is not null
      and revision_kind <> 'initial'
    )
  )
);

create index roof_intelligence_report_revisions_report_idx
  on public.roof_intelligence_report_revisions (report_id, revision_number desc);

create index roof_intelligence_report_revisions_ready_idx
  on public.roof_intelligence_report_revisions (report_id, revision_number desc)
  where generation_status = 'ready';

create table public.roof_intelligence_report_assets (
  id uuid primary key default gen_random_uuid(),
  revision_id uuid not null
    references public.roof_intelligence_report_revisions(id)
    on update cascade
    on delete restrict,
  asset_role text not null check (
    asset_role in ('final_pdf', 'report_image', 'source_image', 'analysis_json', 'other')
  ),
  storage_bucket text not null check (btrim(storage_bucket) <> ''),
  storage_path text not null check (btrim(storage_path) <> ''),
  mime_type text not null check (btrim(mime_type) <> ''),
  size_bytes bigint not null check (size_bytes > 0),
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  is_primary boolean not null default false,
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  unique (storage_bucket, storage_path),
  unique (revision_id, asset_role, storage_path)
);

create unique index roof_intelligence_report_assets_primary_role_key
  on public.roof_intelligence_report_assets (revision_id, asset_role)
  where is_primary;

create index roof_intelligence_report_assets_revision_idx
  on public.roof_intelligence_report_assets (revision_id, asset_role);

create table public.roof_intelligence_notifications (
  id uuid primary key default gen_random_uuid(),
  recipient_id uuid not null references auth.users(id) on delete cascade,
  job_id uuid references public.roof_intelligence_jobs(id) on delete cascade,
  report_id uuid references public.roof_intelligence_reports(id) on delete cascade,
  kind text not null check (btrim(kind) <> ''),
  title text not null check (btrim(title) <> ''),
  message text not null check (btrim(message) <> ''),
  is_read boolean not null default false,
  created_at timestamptz not null default now(),
  read_at timestamptz,
  check ((is_read and read_at is not null) or (not is_read and read_at is null))
);

create index roof_intelligence_notifications_recipient_idx
  on public.roof_intelligence_notifications (recipient_id, is_read, created_at desc);

create table public.roof_intelligence_county_health_checks (
  id uuid primary key default gen_random_uuid(),
  county_key text not null check (btrim(county_key) <> ''),
  status text not null check (status in ('healthy', 'degraded', 'failed')),
  result jsonb not null default '{}'::jsonb check (jsonb_typeof(result) = 'object'),
  checked_at timestamptz not null default now()
);

create index roof_intelligence_county_health_latest_idx
  on public.roof_intelligence_county_health_checks (county_key, checked_at desc);

create or replace function public.set_roof_intelligence_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger roof_intelligence_properties_set_updated_at
before update on public.roof_intelligence_properties
for each row execute function public.set_roof_intelligence_updated_at();

create trigger roof_intelligence_jobs_set_updated_at
before update on public.roof_intelligence_jobs
for each row execute function public.set_roof_intelligence_updated_at();

create trigger roof_intelligence_reports_set_updated_at
before update on public.roof_intelligence_reports
for each row execute function public.set_roof_intelligence_updated_at();

create trigger roof_intelligence_report_revisions_set_updated_at
before update on public.roof_intelligence_report_revisions
for each row execute function public.set_roof_intelligence_updated_at();

create or replace function public.validate_roof_report_revision_lineage()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  parent_report_id uuid;
  parent_revision_number integer;
begin
  if new.parent_revision_id is null then
    return new;
  end if;

  select report_id, revision_number
    into parent_report_id, parent_revision_number
    from public.roof_intelligence_report_revisions
    where id = new.parent_revision_id;

  if parent_report_id is null then
    raise exception 'Parent Roof Intelligence revision does not exist';
  end if;
  if parent_report_id <> new.report_id then
    raise exception 'Parent Roof Intelligence revision belongs to another report';
  end if;
  if parent_revision_number >= new.revision_number then
    raise exception 'Parent Roof Intelligence revision must precede its child revision';
  end if;
  return new;
end;
$$;

create trigger roof_intelligence_report_revisions_validate_lineage
before insert or update on public.roof_intelligence_report_revisions
for each row execute function public.validate_roof_report_revision_lineage();

create or replace function public.prevent_ready_roof_report_revision_changes()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if old.generation_status = 'ready' then
    raise exception 'Ready Roof Intelligence revisions are immutable; create a new revision instead';
  end if;
  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

create trigger roof_intelligence_report_revisions_immutable
before update or delete on public.roof_intelligence_report_revisions
for each row execute function public.prevent_ready_roof_report_revision_changes();

create or replace function public.prevent_ready_roof_report_asset_changes()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  target_revision_id uuid;
  target_status text;
begin
  target_revision_id := case when tg_op = 'DELETE' then old.revision_id else new.revision_id end;
  select generation_status
    into target_status
    from public.roof_intelligence_report_revisions
    where id = target_revision_id;

  if target_status = 'ready' then
    raise exception 'Assets for ready Roof Intelligence revisions are immutable';
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

create trigger roof_intelligence_report_assets_immutable
before insert or update or delete on public.roof_intelligence_report_assets
for each row execute function public.prevent_ready_roof_report_asset_changes();

insert into storage.buckets (id, name, public)
values
  ('roof-intelligence-reports', 'roof-intelligence-reports', false),
  ('roof-intelligence-images', 'roof-intelligence-images', false)
on conflict (id) do update set public = excluded.public;

alter table public.roof_intelligence_properties enable row level security;
alter table public.roof_intelligence_jobs enable row level security;
alter table public.roof_intelligence_job_items enable row level security;
alter table public.roof_intelligence_reports enable row level security;
alter table public.roof_intelligence_report_revisions enable row level security;
alter table public.roof_intelligence_report_assets enable row level security;
alter table public.roof_intelligence_notifications enable row level security;
alter table public.roof_intelligence_county_health_checks enable row level security;

comment on table public.roof_intelligence_properties is
  'Current normalized property identity used by centralized Roof Intelligence reporting.';
comment on table public.roof_intelligence_reports is
  'Stable logical report identity. Generated and edited versions are stored as immutable revisions.';
comment on table public.roof_intelligence_report_revisions is
  'Complete versioned report snapshots. Ready revisions cannot be changed; corrections create a new revision.';
comment on column public.roof_intelligence_report_revisions.generation_status is
  'Technical generation state only. Ready does not imply human review or approval.';
comment on column public.roof_intelligence_report_revisions.calculated_snapshot is
  'Derived values such as roof squares and replacement, overlay, coating, contingency, and warranty calculations.';
comment on column public.roof_intelligence_report_revisions.render_snapshot is
  'Complete resolved input used to reproduce the generated PDF for this revision.';
comment on table public.roof_intelligence_report_assets is
  'Checksummed private Storage objects associated with one report revision.';

-- Deliberately create no browser-facing policies yet. With RLS enabled, these
-- tables and private buckets are closed to anon/authenticated clients. A later
-- PCS authentication migration will add narrowly scoped policies. PilotPoint's
-- trusted worker will use server-side credentials and must never expose the
-- service role in browser or packaged client code.

commit;
