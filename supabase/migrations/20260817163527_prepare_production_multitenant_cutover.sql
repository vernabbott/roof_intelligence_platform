-- Additive, rollback-compatible migration from the August 17, 2026
-- production schema to the tenant-scoped PCS/PilotPoint schema.
--
-- Legacy proposal lifecycle columns intentionally remain on public.proposal.
-- A trigger mirrors normalized proposal_tracking changes back to those columns
-- so the tagged production application remains a viable rollback target.

begin;

set local lock_timeout = '10s';

create extension if not exists pgcrypto;
create schema if not exists private;

create table if not exists public.tenant (
  id uuid primary key default gen_random_uuid(),
  name text not null check (btrim(name) <> ''),
  slug text not null unique check (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.tenant_membership (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenant(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (
    role in ('owner', 'admin', 'sales', 'estimator', 'viewer')
  ),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, user_id)
);

create index if not exists tenant_membership_user_active_idx
  on public.tenant_membership (user_id, tenant_id) where is_active;
create index if not exists tenant_membership_tenant_role_idx
  on public.tenant_membership (tenant_id, role) where is_active;

create table if not exists public.report_folder (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenant(id) on delete cascade,
  name text not null check (btrim(name) <> ''),
  normalized_name text generated always as (
    lower(regexp_replace(btrim(name), '[[:space:]]+', ' ', 'g'))
  ) stored,
  is_archived boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, normalized_name),
  unique (tenant_id, id)
);

create table if not exists public.tenant_settings (
  tenant_id uuid primary key references public.tenant(id) on delete cascade,
  default_report_folder_id uuid,
  company_configuration jsonb not null default '{}'::jsonb
    check (jsonb_typeof(company_configuration) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint tenant_settings_default_report_folder_fkey
    foreign key (tenant_id, default_report_folder_id)
    references public.report_folder(tenant_id, id) on delete restrict
);

create table if not exists public.tenant_feature_flag (
  tenant_id uuid not null references public.tenant(id) on delete cascade,
  feature_key text not null check (feature_key ~ '^[a-z0-9_]+$'),
  enabled boolean not null default false,
  configuration jsonb not null default '{}'::jsonb
    check (jsonb_typeof(configuration) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (tenant_id, feature_key)
);

insert into public.tenant (id, name, slug)
values (
  '00000000-0000-4000-8000-000000000001',
  'Pro Coating Systems',
  'pro-coating-systems'
)
on conflict (id) do update
set name = excluded.name, slug = excluded.slug, is_active = true;

insert into public.report_folder (id, tenant_id, name)
values (
  '00000000-0000-4000-8000-000000000101',
  '00000000-0000-4000-8000-000000000001',
  'Roof Intelligence Reports'
)
on conflict (id) do nothing;

insert into public.tenant_settings (tenant_id, default_report_folder_id)
values (
  '00000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000101'
)
on conflict (tenant_id) do update
set default_report_folder_id = excluded.default_report_folder_id;

-- Large reference tables remain shared. Only tenant-owned business and report
-- records receive tenant_id.
do $tenant_columns$
declare
  table_name text;
  constraint_name text;
begin
  foreach table_name in array array[
    'contact', 'organization', 'organization_contact',
    'property_management_companies', 'property_management_contacts',
    'proposal', 'proposal_contact', 'roof_intelligence_jobs',
    'roof_intelligence_job_items', 'roof_intelligence_reports',
    'roof_intelligence_report_revisions', 'roof_intelligence_report_assets',
    'roof_intelligence_notifications', 'roof_intelligence_report_edit_requests',
    'roof_intelligence_processing_feedback',
    'roof_intelligence_property_overrides'
  ]
  loop
    if to_regclass('public.' || table_name) is not null then
      execute format(
        'alter table public.%I add column if not exists tenant_id uuid',
        table_name
      );
      execute format(
        'update public.%I set tenant_id = $1 where tenant_id is null',
        table_name
      ) using '00000000-0000-4000-8000-000000000001'::uuid;
      execute format(
        'alter table public.%I alter column tenant_id set not null',
        table_name
      );
      constraint_name := table_name || '_tenant_id_fkey';
      if not exists (
        select 1 from pg_constraint
        where conrelid = to_regclass('public.' || table_name)
          and conname = constraint_name
      ) then
        execute format(
          'alter table public.%I add constraint %I foreign key (tenant_id) references public.tenant(id)',
          table_name, constraint_name
        );
      end if;
    end if;
  end loop;
end
$tenant_columns$;

do $report_folder_backfill$
begin
  if to_regclass('public.roof_intelligence_reports') is not null then
    alter table public.roof_intelligence_reports
      add column if not exists report_folder_id uuid;
    update public.roof_intelligence_reports
    set report_folder_id = '00000000-0000-4000-8000-000000000101'
    where report_folder_id is null;
    alter table public.roof_intelligence_reports
      alter column report_folder_id set not null;
    if not exists (
      select 1 from pg_constraint
      where conrelid = 'public.roof_intelligence_reports'::regclass
        and conname = 'roof_intelligence_reports_tenant_folder_fkey'
    ) then
      alter table public.roof_intelligence_reports
        add constraint roof_intelligence_reports_tenant_folder_fkey
        foreign key (tenant_id, report_folder_id)
        references public.report_folder(tenant_id, id) on delete restrict;
    end if;
  end if;
end
$report_folder_backfill$;

-- Replace global uniqueness only where separate tenants may legitimately use
-- the same values.
alter table public.organization
  drop constraint if exists organization_normalized_name_key;
alter table public.organization
  add constraint organization_tenant_normalized_name_key
  unique (tenant_id, normalized_name);

drop index if exists public.contact_linkedin_url_key;
create unique index if not exists contact_tenant_linkedin_url_key
  on public.contact (tenant_id, lower(btrim(linkedin_url)))
  where linkedin_url is not null and btrim(linkedin_url) <> '';

alter table public.proposal
  drop constraint if exists proposal_source_name_source_row_number_key;
alter table public.proposal
  add constraint proposal_tenant_source_row_key
  unique (tenant_id, source_name, source_row_number);
alter table public.proposal
  add constraint proposal_tenant_id_key unique (tenant_id, id);

alter table public.property_management_companies
  drop constraint if exists property_management_companies_normalized_name_key;
alter table public.property_management_companies
  add constraint property_management_companies_tenant_normalized_name_key
  unique (tenant_id, normalized_name);

do $roof_override_uniqueness$
begin
  if to_regclass('public.roof_intelligence_property_overrides') is not null then
    drop index if exists public.roof_intelligence_property_overrides_active_key;
    execute 'create unique index roof_intelligence_property_overrides_tenant_active_key on public.roof_intelligence_property_overrides (tenant_id, property_id, field_name) where revoked_at is null';
  end if;
end
$roof_override_uniqueness$;

create index if not exists contact_tenant_name_idx
  on public.contact (tenant_id, normalized_name);
create index if not exists organization_tenant_active_name_idx
  on public.organization (tenant_id, is_active, normalized_name);
create index if not exists organization_contact_tenant_current_idx
  on public.organization_contact (tenant_id, is_current, normalized_email);

do $tenant_indexes$
begin
  if to_regclass('public.roof_intelligence_jobs') is not null then
    execute 'create index roof_jobs_tenant_status_idx on public.roof_intelligence_jobs (tenant_id, status, queued_at)';
  end if;
  if to_regclass('public.roof_intelligence_job_items') is not null then
    execute 'create index roof_job_items_tenant_job_idx on public.roof_intelligence_job_items (tenant_id, job_id, status)';
  end if;
  if to_regclass('public.roof_intelligence_reports') is not null then
    execute 'create index roof_reports_tenant_created_idx on public.roof_intelligence_reports (tenant_id, created_at desc)';
  end if;
  if to_regclass('public.roof_intelligence_report_revisions') is not null then
    execute 'create index roof_revisions_tenant_report_idx on public.roof_intelligence_report_revisions (tenant_id, report_id, revision_number desc)';
  end if;
  if to_regclass('public.roof_intelligence_report_assets') is not null then
    execute 'create index roof_assets_tenant_revision_idx on public.roof_intelligence_report_assets (tenant_id, revision_id)';
  end if;
  if to_regclass('public.roof_intelligence_notifications') is not null then
    execute 'create index roof_notifications_tenant_recipient_idx on public.roof_intelligence_notifications (tenant_id, recipient_id, is_read, created_at desc)';
  end if;
  if to_regclass('public.roof_intelligence_report_edit_requests') is not null then
    execute 'create index roof_edit_requests_tenant_status_idx on public.roof_intelligence_report_edit_requests (tenant_id, status, created_at)';
  end if;
  if to_regclass('public.roof_intelligence_processing_feedback') is not null then
    execute 'create index roof_feedback_tenant_status_idx on public.roof_intelligence_processing_feedback (tenant_id, status, created_at)';
  end if;
end
$tenant_indexes$;

-- Proposal identity stays in proposal. Lifecycle and assignment data is copied
-- one-to-one to proposal_tracking without dropping the legacy columns.
create table public.proposal_tracking (
  proposal_id uuid primary key,
  tenant_id uuid not null references public.tenant(id),
  proposal_display_name text not null,
  submitted_by text,
  estimated_by text,
  estimate_completed_date date,
  proposal_sent_date date,
  follow_up_date date,
  follow_up_required boolean not null default true,
  lead_source text,
  response_notes text,
  status text not null default 'draft' check (
    status in ('draft', 'sent', 'under_contract', 'finished', 'dead')
  ),
  source_name text,
  source_row_number integer check (
    source_row_number is null or source_row_number >= 2
  ),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint proposal_tracking_proposal_tenant_fkey
    foreign key (tenant_id, proposal_id)
    references public.proposal(tenant_id, id) on delete cascade,
  constraint proposal_tracking_tenant_source_row_key
    unique (tenant_id, source_name, source_row_number)
);

insert into public.proposal_tracking (
  proposal_id, tenant_id, proposal_display_name, submitted_by, estimated_by,
  estimate_completed_date, proposal_sent_date, follow_up_date,
  follow_up_required, lead_source, response_notes, status, source_name,
  source_row_number, created_at, updated_at
)
select
  id, tenant_id, display_name, submitted_by, estimated_by,
  estimate_completed_date, proposal_sent_date, follow_up_date,
  true, lead_source, response_notes,
  case
    when status in ('draft', 'sent', 'under_contract', 'finished', 'dead')
      then status
    when status = 'won' then 'under_contract'
    when status in ('lost', 'withdrawn', 'archived') then 'dead'
    else case when proposal_sent_date is null then 'draft' else 'sent' end
  end,
  source_name, source_row_number, created_at, updated_at
from public.proposal;

-- These immutable proposal IDs correspond to the 88 production spreadsheet
-- rows whose Follow-Up value was '-'. They were previously verified against
-- the reconciled beta database.
update public.proposal_tracking
set follow_up_required = false
where proposal_id in (
  '052485ba-5f8f-4ab3-b863-1deadd9852ea',
  '057f5496-189d-4df4-9c2d-768b8c63a796',
  '062516ce-2e7b-4359-af0d-a99417af0b5c',
  '090ee3c2-1864-472a-a7a0-96fc5d82c2b5',
  '0b16964e-6c59-4d49-96f4-28cbf2e2aa1f',
  '0e50f11b-e6f5-40b0-bba0-11808cc442fa',
  '13e5df2d-1669-4741-aa7f-266eab6f8e72',
  '15f3ada3-3f3a-442f-9eab-960f7fa1dad7',
  '17e3d41e-a257-483b-8ab7-5479a717d70e',
  '18b07707-3639-4a5f-a490-0d78dd1066f5',
  '18d9aa7d-d3a4-4e15-b47a-7feab7e894dd',
  '1c3d949f-5508-4106-bd7a-7daeab1cab39',
  '1d8536b5-3103-4a78-9f81-d481bff5fa82',
  '1e03b318-f091-47f7-9891-fee2008fd835',
  '1f10af1b-0d82-498c-a541-02bc47e40d2d',
  '200f57a4-02e5-4d29-bffd-b470c4c2a786',
  '24c07bea-a6fd-4df9-96ff-29ce3d6afde6',
  '2bc03eb1-19c2-4bfd-9b1c-61b52143ab72',
  '2dbad9e8-17ba-42ea-9712-543fa1495f7a',
  '2ee681cd-90f5-49ad-8822-50c4148b43b6',
  '31e1a7da-e8cf-42fb-81be-0980bed651b3',
  '351e7986-a5ea-4a25-b264-a08afc0a1101',
  '37cb4c2b-7e4b-46cd-bbdd-4f6a3936162b',
  '38d34c46-0d23-4187-b7ba-341c4ac21da1',
  '39f6a21f-eb75-4934-925c-b36ed5bb12d1',
  '3be0553b-953c-4d34-b5c1-483b8a34d16e',
  '3d86faa6-7577-4be7-abbe-c7a929f645c7',
  '41813c3f-b6fa-4051-8915-4bc3c7432bbf',
  '44a947a3-3907-4e3f-8af1-8e403a7597ba',
  '45debcb3-03c9-4627-900d-8288f0bf019e',
  '4715b6b0-3aec-4daf-a754-03ab2013876c',
  '4e456c36-777e-4b15-9532-41250f4a3cb7',
  '4e46fde7-87d4-416b-99ce-e63418ae6e51',
  '4ebbd124-7418-4a09-8b31-c6370b5cee32',
  '59343475-15ef-4b80-b189-5d022dc2dcaa',
  '62d60453-81d0-4b4e-95d3-f35191eb800f',
  '66ff55f6-c1a4-48a7-96ad-a5c4d6bf982a',
  '6c4712f6-905a-43b7-8c1e-ee6d6f04a3c5',
  '6f88b4fa-83f6-414e-9763-0eb0b5f55a1f',
  '707ffe9b-8deb-4622-a81c-b08057cdaa47',
  '761c0768-8462-4111-bcbc-20783fe9eac6',
  '780233ad-ca69-43a7-be6e-d2db21eea83a',
  '79a7dd92-3a04-4afe-a686-5c64a678f8a9',
  '806fdae0-cf85-47d1-97a0-5653415157e3',
  '84dfb195-4387-4c35-9bea-d70bfc86976f',
  '872b670c-6b8b-48d4-a29e-8f6764222a76',
  '8d8a635c-4a81-4b26-acee-f2e01dfa843b',
  '91afd6f9-1dec-490a-99d8-edaacb73119d',
  '9268f81d-d756-498e-8955-a50afbd1323e',
  '98deed69-50c6-4156-9677-11720f2b337b',
  '994fc033-3a50-4fef-b60c-0e1441dbda11',
  'a03c795b-2ece-4da4-a140-8b09100fdbd7',
  'a3062c4a-fbbb-494f-9ff2-43a714d2e13f',
  'a51aae08-8407-4750-9a42-fdfe0627ae51',
  'a9f0a522-d457-4602-9fbb-13456b6f6c52',
  'aa626c9e-7116-4b71-b7b1-597207ab9156',
  'ad612661-09c7-4d49-80cc-2d16755c6cf1',
  'ae1a5a34-6c02-44a8-ae4c-69b39b9534d6',
  'b391ba71-4c98-4d78-8652-762d91b66dd5',
  'bdaa881f-d78d-4706-b87e-4ac2f0e7e74a',
  'bdf0a6b1-024a-4efe-ba43-3ba6bcc7aaa3',
  'bdf77371-add7-4164-8549-8e669c81e518',
  'c13489d0-7a43-44c7-a3f5-e69d7e64d421',
  'c86394a1-5bf0-4734-9618-5c0732b8ea15',
  'c8f31d16-31de-4c3b-9931-f469e66c4247',
  'c91103cb-4675-4734-a38e-9dce66d0e197',
  'cd8144c4-876b-4ef1-bda0-1593d6182f7b',
  'ce575498-8115-455a-af66-0ca543246a15',
  'cf0b73e1-205a-4280-b609-9847cc668372',
  'd0b352ac-1c62-4e6b-ad6a-3c6fe7a4146c',
  'd101f071-3546-420c-a930-4ce9eea98e20',
  'd2ab1f45-c8ee-45bc-b14c-bcfad25f3bf4',
  'd65610b1-079f-40a9-aba9-b32118707369',
  'd6896221-1420-488c-9c60-32bcfaa22bda',
  'd70a7fb0-4b35-4746-8ace-a422a2ebb411',
  'd7e9212f-eebd-4346-b072-78d0c4f89fd7',
  'd897c4e4-dd39-4f24-a175-33220759140b',
  'da53faea-8fe7-4b4f-8904-4754b636fbee',
  'dceb8029-87eb-49a2-a09e-8fb41c431f42',
  'e2b66262-ee88-423d-9d0e-46198ea27c28',
  'e2be804f-f504-4ab0-8b66-3113d071b227',
  'e339807c-d6db-42e8-900b-59efa4fe0f6a',
  'e53bb641-263b-4831-965a-38aa25ec6cd0',
  'e7f9e889-5daf-4f45-9b90-e412030ea910',
  'eb77f2f4-3c64-4c4f-9c39-447a4c36c927',
  'eb8fa2cf-cc1b-4408-8968-63e180c6705c',
  'ec20a58c-42c9-429e-83c1-8a63f9ae04ca',
  'ef750c5c-f59e-46d3-8f7c-1fa4e45d5ba5'
);

do $proposal_validation$
declare
  proposal_count bigint;
  tracking_count bigint;
begin
  select count(*) into proposal_count from public.proposal;
  select count(*) into tracking_count from public.proposal_tracking;
  if proposal_count <> tracking_count then
    raise exception
      'Proposal tracking migration changed row count: proposal %, tracking %',
      proposal_count, tracking_count;
  end if;
  if (
    select count(*) from public.proposal_tracking where not follow_up_required
  ) <> 88 then
    raise exception 'Expected 88 proposal rows with follow_up_required=false';
  end if;
  if exists (
    select 1
    from public.proposal proposal
    join public.proposal_tracking tracking
      on tracking.proposal_id = proposal.id
    where row(
      tracking.tenant_id, tracking.proposal_display_name,
      tracking.submitted_by, tracking.estimated_by,
      tracking.estimate_completed_date, tracking.proposal_sent_date,
      tracking.follow_up_date, tracking.lead_source,
      tracking.response_notes, tracking.status, tracking.source_name,
      tracking.source_row_number
    ) is distinct from row(
      proposal.tenant_id, proposal.display_name,
      proposal.submitted_by, proposal.estimated_by,
      proposal.estimate_completed_date, proposal.proposal_sent_date,
      proposal.follow_up_date, proposal.lead_source,
      proposal.response_notes, proposal.status, proposal.source_name,
      proposal.source_row_number
    )
  ) then
    raise exception 'Proposal tracking migration changed lifecycle data';
  end if;
end
$proposal_validation$;

create index proposal_tracking_tenant_status_sent_idx
  on public.proposal_tracking (tenant_id, status, proposal_sent_date desc);
create index proposal_tracking_tenant_follow_up_queue_idx
  on public.proposal_tracking (tenant_id, proposal_sent_date, follow_up_date)
  where proposal_sent_date is not null
    and follow_up_date is null
    and follow_up_required;

alter table public.proposal
  add column if not exists draft_detail jsonb not null default '{}'::jsonb
  check (jsonb_typeof(draft_detail) = 'object');

create or replace function public.set_proposal_tracking_display_name()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
begin
  select proposal.display_name
  into new.proposal_display_name
  from public.proposal as proposal
  where proposal.tenant_id = new.tenant_id
    and proposal.id = new.proposal_id;
  if new.proposal_display_name is null then
    raise exception 'Proposal % does not belong to tenant %',
      new.proposal_id, new.tenant_id;
  end if;
  return new;
end
$function$;

create or replace function public.sync_proposal_display_name_to_tracking()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
begin
  update public.proposal_tracking
  set proposal_display_name = new.display_name
  where tenant_id = new.tenant_id and proposal_id = new.id;
  return new;
end
$function$;

create or replace function public.sync_proposal_tracking_to_legacy()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
begin
  update public.proposal
  set
    submitted_by = new.submitted_by,
    estimated_by = new.estimated_by,
    estimate_completed_date = new.estimate_completed_date,
    proposal_sent_date = new.proposal_sent_date,
    follow_up_date = new.follow_up_date,
    lead_source = new.lead_source,
    response_notes = new.response_notes,
    status = new.status,
    source_name = new.source_name,
    source_row_number = new.source_row_number
  where id = new.proposal_id and tenant_id = new.tenant_id;
  return new;
end
$function$;

create trigger proposal_tracking_set_display_name
before insert or update on public.proposal_tracking
for each row execute function public.set_proposal_tracking_display_name();
create trigger proposal_tracking_set_updated_at
before update on public.proposal_tracking
for each row execute function public.set_property_management_updated_at();
create trigger proposal_tracking_sync_legacy
after insert or update on public.proposal_tracking
for each row execute function public.sync_proposal_tracking_to_legacy();
create trigger proposal_sync_display_name_to_tracking
after update of customer_name, project_street_address on public.proposal
for each row
when (old.display_name is distinct from new.display_name)
execute function public.sync_proposal_display_name_to_tracking();

-- Database-level relationship checks also protect service-role worker writes.
create or replace function private.enforce_tenant_parent()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  parent_tenant uuid;
begin
  execute format(
    'select tenant_id from %I.%I where id = $1', tg_argv[0], tg_argv[1]
  ) into parent_tenant using (to_jsonb(new) ->> tg_argv[2])::uuid;
  if parent_tenant is null or parent_tenant <> new.tenant_id then
    raise exception 'Cross-tenant relationship is not allowed';
  end if;
  return new;
end
$function$;

create or replace function private.set_tenant_from_parent()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  parent_tenant uuid;
begin
  execute format(
    'select tenant_id from %I.%I where id = $1', tg_argv[0], tg_argv[1]
  ) into parent_tenant using (to_jsonb(new) ->> tg_argv[2])::uuid;
  if parent_tenant is null then
    raise exception 'The tenant-owning parent record was not found';
  end if;
  if new.tenant_id is not null and new.tenant_id <> parent_tenant then
    raise exception 'Cross-tenant relationship is not allowed';
  end if;
  new.tenant_id := parent_tenant;
  return new;
end
$function$;

create or replace function private.set_job_tenant()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  derived_tenant uuid;
begin
  if new.tenant_id is not null then
    return new;
  end if;
  if new.job_type = 'report_revision' and new.input ? 'report_id' then
    select tenant_id into derived_tenant
    from public.roof_intelligence_reports
    where id = (new.input ->> 'report_id')::uuid;
  elsif new.requested_by is not null then
    select min(tenant_id::text)::uuid into derived_tenant
    from public.tenant_membership
    where user_id = new.requested_by and is_active;
  end if;
  if derived_tenant is null then
    raise exception
      'A trusted tenant context is required to create a Roof Intelligence job';
  end if;
  new.tenant_id := derived_tenant;
  return new;
end
$function$;

create or replace function private.set_report_tenant_and_folder()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  job_tenant uuid;
begin
  if new.source_job_id is not null then
    select tenant_id into job_tenant
    from public.roof_intelligence_jobs where id = new.source_job_id;
    if new.tenant_id is not null and new.tenant_id <> job_tenant then
      raise exception 'Cross-tenant report creation is not allowed';
    end if;
    new.tenant_id := job_tenant;
  end if;
  if new.tenant_id is null then
    raise exception 'A trusted tenant context is required to create a report';
  end if;
  if new.report_folder_id is null then
    select default_report_folder_id into new.report_folder_id
    from public.tenant_settings where tenant_id = new.tenant_id;
  end if;
  if new.report_folder_id is null then
    raise exception 'The tenant does not have a default report folder';
  end if;
  return new;
end
$function$;

create or replace function private.validate_tenant_storage_path()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  revision_report_id uuid;
  folder_id uuid;
  expected_prefix text;
begin
  select revision.report_id, report.report_folder_id
  into revision_report_id, folder_id
  from public.roof_intelligence_report_revisions revision
  join public.roof_intelligence_reports report
    on report.id = revision.report_id
  where revision.id = new.revision_id
    and revision.tenant_id = new.tenant_id;
  expected_prefix := new.tenant_id::text || '/folders/' || folder_id::text ||
    '/reports/' || revision_report_id::text || '/revisions/';
  if new.storage_path not like expected_prefix || '%' then
    raise exception 'Storage path is outside the report tenant namespace';
  end if;
  return new;
end
$function$;

create or replace function private.set_notification_tenant()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  derived_tenant uuid;
begin
  if new.report_id is not null then
    select tenant_id into derived_tenant
    from public.roof_intelligence_reports where id = new.report_id;
  elsif new.job_id is not null then
    select tenant_id into derived_tenant
    from public.roof_intelligence_jobs where id = new.job_id;
  end if;
  if derived_tenant is null
    or (new.tenant_id is not null and new.tenant_id <> derived_tenant)
  then
    raise exception 'A notification must use the tenant of its job or report';
  end if;
  new.tenant_id := derived_tenant;
  return new;
end
$function$;

create or replace function private.validate_edit_request_actor()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
begin
  if (select auth.uid()) is not null and (
    new.requested_by <> (select auth.uid())
    or not private.user_has_tenant_access(new.tenant_id)
  ) then
    raise exception 'The report is outside the authenticated tenant';
  end if;
  return new;
end
$function$;

do $relationship_triggers$
begin
  drop trigger if exists organization_contact_contact_tenant
    on public.organization_contact;
  create trigger organization_contact_contact_tenant
    before insert or update on public.organization_contact for each row
    execute function private.enforce_tenant_parent(
      'public', 'contact', 'contact_id'
    );
  drop trigger if exists organization_contact_organization_tenant
    on public.organization_contact;
  create trigger organization_contact_organization_tenant
    before insert or update on public.organization_contact for each row
    execute function private.enforce_tenant_parent(
      'public', 'organization', 'organization_id'
    );
  drop trigger if exists proposal_contact_proposal_tenant
    on public.proposal_contact;
  create trigger proposal_contact_proposal_tenant
    before insert or update on public.proposal_contact for each row
    execute function private.enforce_tenant_parent(
      'public', 'proposal', 'proposal_id'
    );
  drop trigger if exists proposal_contact_relationship_tenant
    on public.proposal_contact;
  create trigger proposal_contact_relationship_tenant
    before insert or update on public.proposal_contact for each row
    execute function private.enforce_tenant_parent(
      'public', 'organization_contact', 'organization_contact_id'
    );
end
$relationship_triggers$;

do $roof_triggers$
begin
  if to_regclass('public.roof_intelligence_jobs') is not null then
    execute 'create trigger a_roof_job_set_tenant before insert or update on public.roof_intelligence_jobs for each row execute function private.set_job_tenant()';
  end if;
  if to_regclass('public.roof_intelligence_job_items') is not null then
    execute $sql$create trigger a_roof_job_item_set_tenant before insert or update on public.roof_intelligence_job_items for each row execute function private.set_tenant_from_parent('public', 'roof_intelligence_jobs', 'job_id')$sql$;
    execute $sql$create trigger roof_job_item_job_tenant before insert or update on public.roof_intelligence_job_items for each row execute function private.enforce_tenant_parent('public', 'roof_intelligence_jobs', 'job_id')$sql$;
  end if;
  if to_regclass('public.roof_intelligence_reports') is not null then
    execute 'create trigger a_roof_report_set_tenant_and_folder before insert or update on public.roof_intelligence_reports for each row execute function private.set_report_tenant_and_folder()';
  end if;
  if to_regclass('public.roof_intelligence_report_revisions') is not null then
    execute $sql$create trigger a_roof_revision_set_tenant before insert or update on public.roof_intelligence_report_revisions for each row execute function private.set_tenant_from_parent('public', 'roof_intelligence_reports', 'report_id')$sql$;
    execute $sql$create trigger roof_revision_report_tenant before insert or update on public.roof_intelligence_report_revisions for each row execute function private.enforce_tenant_parent('public', 'roof_intelligence_reports', 'report_id')$sql$;
  end if;
  if to_regclass('public.roof_intelligence_report_assets') is not null then
    execute $sql$create trigger a_roof_asset_set_tenant before insert or update on public.roof_intelligence_report_assets for each row execute function private.set_tenant_from_parent('public', 'roof_intelligence_report_revisions', 'revision_id')$sql$;
    execute $sql$create trigger roof_asset_revision_tenant before insert or update on public.roof_intelligence_report_assets for each row execute function private.enforce_tenant_parent('public', 'roof_intelligence_report_revisions', 'revision_id')$sql$;
    execute 'create trigger roof_asset_validate_tenant_path before insert or update on public.roof_intelligence_report_assets for each row execute function private.validate_tenant_storage_path()';
  end if;
  if to_regclass('public.roof_intelligence_notifications') is not null then
    execute 'create trigger a_roof_notification_set_tenant before insert or update on public.roof_intelligence_notifications for each row execute function private.set_notification_tenant()';
  end if;
  if to_regclass('public.roof_intelligence_report_edit_requests') is not null then
    execute $sql$create trigger a_roof_edit_request_set_tenant before insert or update on public.roof_intelligence_report_edit_requests for each row execute function private.set_tenant_from_parent('public', 'roof_intelligence_reports', 'report_id')$sql$;
    execute 'create trigger b_roof_edit_request_validate_actor before insert or update on public.roof_intelligence_report_edit_requests for each row execute function private.validate_edit_request_actor()';
    execute $sql$create trigger roof_edit_request_report_tenant before insert or update on public.roof_intelligence_report_edit_requests for each row execute function private.enforce_tenant_parent('public', 'roof_intelligence_reports', 'report_id')$sql$;
  end if;
  if to_regclass('public.roof_intelligence_processing_feedback') is not null then
    execute $sql$create trigger a_roof_feedback_set_tenant before insert or update on public.roof_intelligence_processing_feedback for each row execute function private.set_tenant_from_parent('public', 'roof_intelligence_reports', 'report_id')$sql$;
    execute $sql$create trigger roof_feedback_report_tenant before insert or update on public.roof_intelligence_processing_feedback for each row execute function private.enforce_tenant_parent('public', 'roof_intelligence_reports', 'report_id')$sql$;
  end if;
  if to_regclass('public.roof_intelligence_property_overrides') is not null then
    execute $sql$create trigger a_roof_override_set_tenant before insert or update on public.roof_intelligence_property_overrides for each row execute function private.set_tenant_from_parent('public', 'roof_intelligence_report_revisions', 'source_revision_id')$sql$;
  end if;
end
$roof_triggers$;

-- Authorization helpers are SECURITY DEFINER solely so membership checks are
-- not blocked by tenant_membership RLS. They validate auth.uid() internally,
-- live in the private schema, and are not executable by PUBLIC or anon.
create or replace function private.user_has_tenant_access(
  target_tenant_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
  select exists (
    select 1
    from public.tenant_membership membership
    join public.tenant tenant_record
      on tenant_record.id = membership.tenant_id
    where membership.tenant_id = target_tenant_id
      and membership.user_id = (select auth.uid())
      and membership.is_active
      and tenant_record.is_active
  );
$function$;

create or replace function private.user_is_tenant_administrator(
  target_tenant_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
  select exists (
    select 1
    from public.tenant_membership membership
    where membership.tenant_id = target_tenant_id
      and membership.user_id = (select auth.uid())
      and membership.is_active
      and membership.role in ('owner', 'admin')
  );
$function$;

create or replace function private.user_has_tenant_role(
  target_tenant_id uuid,
  allowed_roles text[]
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
  select exists (
    select 1
    from public.tenant_membership membership
    join public.tenant tenant_record
      on tenant_record.id = membership.tenant_id
    where membership.tenant_id = target_tenant_id
      and membership.user_id = (select auth.uid())
      and membership.is_active
      and tenant_record.is_active
      and membership.role = any(allowed_roles)
  );
$function$;

revoke all on schema private from public, anon;
grant usage on schema private to authenticated;
revoke all on function private.user_has_tenant_access(uuid)
  from public, anon;
revoke all on function private.user_is_tenant_administrator(uuid)
  from public, anon;
revoke all on function private.user_has_tenant_role(uuid, text[])
  from public, anon;
grant execute on function private.user_has_tenant_access(uuid)
  to authenticated;
grant execute on function private.user_is_tenant_administrator(uuid)
  to authenticated;
grant execute on function private.user_has_tenant_role(uuid, text[])
  to authenticated;

alter table public.tenant enable row level security;
alter table public.tenant_membership enable row level security;
alter table public.report_folder enable row level security;
alter table public.tenant_settings enable row level security;
alter table public.tenant_feature_flag enable row level security;
alter table public.proposal_tracking enable row level security;

create policy tenant_member_read on public.tenant for select to authenticated
  using (private.user_has_tenant_access(id));

-- One SELECT policy avoids the multiple-permissive-policy advisor warning.
create policy membership_visible_read
on public.tenant_membership for select to authenticated
using (
  (user_id = (select auth.uid()) and is_active)
  or private.user_is_tenant_administrator(tenant_id)
);
create policy membership_admin_insert
on public.tenant_membership for insert to authenticated
with check (private.user_is_tenant_administrator(tenant_id));
create policy membership_admin_update
on public.tenant_membership for update to authenticated
using (private.user_is_tenant_administrator(tenant_id))
with check (private.user_is_tenant_administrator(tenant_id));
create policy membership_admin_delete
on public.tenant_membership for delete to authenticated
using (private.user_is_tenant_administrator(tenant_id));

create policy report_folder_tenant_read
on public.report_folder for select to authenticated
using (private.user_has_tenant_access(tenant_id));
create policy report_folder_tenant_admin_insert
on public.report_folder for insert to authenticated
with check (private.user_is_tenant_administrator(tenant_id));
create policy report_folder_tenant_admin_update
on public.report_folder for update to authenticated
using (private.user_is_tenant_administrator(tenant_id))
with check (private.user_is_tenant_administrator(tenant_id));
create policy report_folder_tenant_admin_delete
on public.report_folder for delete to authenticated
using (private.user_is_tenant_administrator(tenant_id));

create policy tenant_settings_tenant_read
on public.tenant_settings for select to authenticated
using (private.user_has_tenant_access(tenant_id));
create policy tenant_settings_tenant_admin_insert
on public.tenant_settings for insert to authenticated
with check (private.user_is_tenant_administrator(tenant_id));
create policy tenant_settings_tenant_admin_update
on public.tenant_settings for update to authenticated
using (private.user_is_tenant_administrator(tenant_id))
with check (private.user_is_tenant_administrator(tenant_id));
create policy tenant_settings_tenant_admin_delete
on public.tenant_settings for delete to authenticated
using (private.user_is_tenant_administrator(tenant_id));

create policy tenant_feature_flag_tenant_read
on public.tenant_feature_flag for select to authenticated
using (private.user_has_tenant_access(tenant_id));
create policy tenant_feature_flag_tenant_admin_insert
on public.tenant_feature_flag for insert to authenticated
with check (private.user_is_tenant_administrator(tenant_id));
create policy tenant_feature_flag_tenant_admin_update
on public.tenant_feature_flag for update to authenticated
using (private.user_is_tenant_administrator(tenant_id))
with check (private.user_is_tenant_administrator(tenant_id));
create policy tenant_feature_flag_tenant_admin_delete
on public.tenant_feature_flag for delete to authenticated
using (private.user_is_tenant_administrator(tenant_id));

create policy proposal_tracking_tenant_read
on public.proposal_tracking for select to authenticated
using (private.user_has_tenant_access(tenant_id));
create policy proposal_tracking_tenant_insert
on public.proposal_tracking for insert to authenticated
with check (
  private.user_has_tenant_role(
    tenant_id, array['owner', 'admin', 'sales', 'estimator']
  )
);
create policy proposal_tracking_tenant_update
on public.proposal_tracking for update to authenticated
using (
  private.user_has_tenant_role(
    tenant_id, array['owner', 'admin', 'sales', 'estimator']
  )
)
with check (
  private.user_has_tenant_role(
    tenant_id, array['owner', 'admin', 'sales', 'estimator']
  )
);
create policy proposal_tracking_tenant_delete
on public.proposal_tracking for delete to authenticated
using (private.user_is_tenant_administrator(tenant_id));

-- Replace broad pre-tenant policies and grant authenticated Data API access
-- only through tenant-scoped RLS.
do $legacy_policy_cleanup$
begin
  if to_regclass('public.roof_intelligence_jobs') is not null then
    drop policy if exists roof_intelligence_jobs_authenticated_read
      on public.roof_intelligence_jobs;
  end if;
  if to_regclass('public.roof_intelligence_job_items') is not null then
    drop policy if exists roof_intelligence_job_items_authenticated_read
      on public.roof_intelligence_job_items;
  end if;
  if to_regclass('public.roof_intelligence_reports') is not null then
    drop policy if exists roof_intelligence_reports_authenticated_read
      on public.roof_intelligence_reports;
  end if;
  if to_regclass('public.roof_intelligence_report_revisions') is not null then
    drop policy if exists roof_intelligence_report_revisions_authenticated_read
      on public.roof_intelligence_report_revisions;
  end if;
  if to_regclass('public.roof_intelligence_report_assets') is not null then
    drop policy if exists roof_intelligence_report_assets_authenticated_read
      on public.roof_intelligence_report_assets;
  end if;
  if to_regclass('public.roof_intelligence_notifications') is not null then
    drop policy if exists roof_intelligence_notifications_recipient_read
      on public.roof_intelligence_notifications;
  end if;
  if to_regclass('public.roof_intelligence_report_edit_requests') is not null then
    drop policy if exists roof_intelligence_edit_requests_authenticated_read
      on public.roof_intelligence_report_edit_requests;
  end if;
  if to_regclass('public.roof_intelligence_processing_feedback') is not null then
    drop policy if exists roof_intelligence_processing_feedback_authenticated_read
      on public.roof_intelligence_processing_feedback;
  end if;
  if to_regclass('public.roof_intelligence_property_overrides') is not null then
    drop policy if exists roof_intelligence_property_overrides_authenticated_read
      on public.roof_intelligence_property_overrides;
  end if;
end
$legacy_policy_cleanup$;

do $business_policies$
declare
  table_name text;
begin
  foreach table_name in array array[
    'contact', 'organization', 'organization_contact',
    'property_management_companies', 'property_management_contacts',
    'proposal', 'proposal_contact', 'roof_intelligence_jobs',
    'roof_intelligence_job_items', 'roof_intelligence_reports',
    'roof_intelligence_report_revisions', 'roof_intelligence_report_assets',
    'roof_intelligence_notifications', 'roof_intelligence_report_edit_requests',
    'roof_intelligence_processing_feedback',
    'roof_intelligence_property_overrides'
  ]
  loop
    if to_regclass('public.' || table_name) is not null then
      execute format('alter table public.%I enable row level security', table_name);
      execute format('drop policy if exists %I on public.%I', table_name || '_tenant_read', table_name);
      execute format('drop policy if exists %I on public.%I', table_name || '_tenant_insert', table_name);
      execute format('drop policy if exists %I on public.%I', table_name || '_tenant_update', table_name);
      execute format('drop policy if exists %I on public.%I', table_name || '_tenant_delete', table_name);
      execute format(
        'create policy %I on public.%I for select to authenticated using (private.user_has_tenant_access(tenant_id))',
        table_name || '_tenant_read', table_name
      );
      execute format(
        'create policy %I on public.%I for insert to authenticated with check (private.user_has_tenant_role(tenant_id, array[''owner'',''admin'',''sales'',''estimator'']))',
        table_name || '_tenant_insert', table_name
      );
      execute format(
        'create policy %I on public.%I for update to authenticated using (private.user_has_tenant_role(tenant_id, array[''owner'',''admin'',''sales'',''estimator''])) with check (private.user_has_tenant_role(tenant_id, array[''owner'',''admin'',''sales'',''estimator'']))',
        table_name || '_tenant_update', table_name
      );
      execute format(
        'create policy %I on public.%I for delete to authenticated using (private.user_is_tenant_administrator(tenant_id))',
        table_name || '_tenant_delete', table_name
      );
      execute format(
        'grant select, insert, update, delete on table public.%I to authenticated, service_role',
        table_name
      );
    end if;
  end loop;
end
$business_policies$;

do $notification_policy$
begin
  if to_regclass('public.roof_intelligence_notifications') is not null then
    drop policy roof_intelligence_notifications_tenant_read
      on public.roof_intelligence_notifications;
    create policy roof_intelligence_notifications_tenant_read
    on public.roof_intelligence_notifications for select to authenticated
    using (
      private.user_has_tenant_access(tenant_id)
      and (
        recipient_id = (select auth.uid())
        or private.user_is_tenant_administrator(tenant_id)
      )
    );
  end if;
end
$notification_policy$;

grant select on public.tenant, public.tenant_membership to authenticated;
grant select, insert, update, delete on
  public.report_folder,
  public.tenant_settings,
  public.tenant_feature_flag,
  public.proposal_tracking
to authenticated;
grant select, insert, update, delete on
  public.tenant,
  public.tenant_membership,
  public.report_folder,
  public.tenant_settings,
  public.tenant_feature_flag,
  public.proposal_tracking
to service_role;

do $storage_policies$
begin
  if to_regclass('storage.objects') is not null then
    drop policy if exists tenant_storage_read on storage.objects;
    drop policy if exists tenant_storage_insert on storage.objects;
    drop policy if exists tenant_storage_update on storage.objects;
    create policy tenant_storage_read
    on storage.objects for select to authenticated
    using (
      bucket_id in ('roof-intelligence-reports', 'roof-intelligence-images')
      and exists (
        select 1 from public.tenant_membership membership
        where membership.user_id = (select auth.uid())
          and membership.is_active
          and membership.tenant_id::text = (storage.foldername(name))[1]
      )
    );
    create policy tenant_storage_insert
    on storage.objects for insert to authenticated
    with check (
      bucket_id in ('roof-intelligence-reports', 'roof-intelligence-images')
      and exists (
        select 1 from public.tenant_membership membership
        where membership.user_id = (select auth.uid())
          and membership.is_active
          and membership.tenant_id::text = (storage.foldername(name))[1]
      )
    );
    create policy tenant_storage_update
    on storage.objects for update to authenticated
    using (
      bucket_id in ('roof-intelligence-reports', 'roof-intelligence-images')
      and exists (
        select 1 from public.tenant_membership membership
        where membership.user_id = (select auth.uid())
          and membership.is_active
          and membership.tenant_id::text = (storage.foldername(name))[1]
      )
    )
    with check (
      bucket_id in ('roof-intelligence-reports', 'roof-intelligence-images')
      and exists (
        select 1 from public.tenant_membership membership
        where membership.user_id = (select auth.uid())
          and membership.is_active
          and membership.tenant_id::text = (storage.foldername(name))[1]
      )
    );
  end if;
end
$storage_policies$;

comment on table public.tenant is
  'Licensed company boundary for tenant-owned PCS and PilotPoint data.';
comment on table public.proposal is
  'Proposal customer and project identity. Legacy lifecycle columns remain temporarily for rollback compatibility.';
comment on table public.proposal_tracking is
  'Tenant-scoped one-to-one lifecycle, assignment, response, and import metadata for a proposal.';
comment on column public.proposal_tracking.follow_up_required is
  'False when no future proposal follow-up is intended.';
comment on column public.tenant_settings.company_configuration is
  'Tenant-owned application configuration; typed application defaults remain fallback values during migration.';

notify pgrst, 'reload schema';

commit;
