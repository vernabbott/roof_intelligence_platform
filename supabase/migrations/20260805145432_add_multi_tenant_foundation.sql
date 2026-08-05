-- Permanent multi-tenant foundation for the beta applications.
-- Large reference datasets (footprints and normalized properties) remain shared.

begin;

create extension if not exists pgcrypto;
create schema if not exists private;

create table public.tenant (
  id uuid primary key default gen_random_uuid(),
  name text not null check (btrim(name) <> ''),
  slug text not null unique check (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.tenant_membership (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenant(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('owner', 'admin', 'sales', 'estimator', 'viewer')),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, user_id)
);

create index tenant_membership_user_active_idx
  on public.tenant_membership (user_id, tenant_id) where is_active;
create index tenant_membership_tenant_role_idx
  on public.tenant_membership (tenant_id, role) where is_active;

create table public.report_folder (
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

create table public.tenant_settings (
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

create table public.tenant_feature_flag (
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
values ('00000000-0000-4000-8000-000000000001', 'Pro Coating Systems', 'pro-coating-systems')
on conflict (id) do nothing;

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
on conflict (tenant_id) do nothing;

-- Add explicit ownership to business records. Reference data stays global.
alter table public.contact add column tenant_id uuid references public.tenant(id);
alter table public.organization add column tenant_id uuid references public.tenant(id);
alter table public.organization_contact add column tenant_id uuid references public.tenant(id);
alter table public.property_management_companies add column tenant_id uuid references public.tenant(id);
alter table public.property_management_contacts add column tenant_id uuid references public.tenant(id);
alter table public.proposal add column tenant_id uuid references public.tenant(id);
alter table public.proposal_contact add column tenant_id uuid references public.tenant(id);
alter table public.roof_intelligence_jobs add column tenant_id uuid references public.tenant(id);
alter table public.roof_intelligence_job_items add column tenant_id uuid references public.tenant(id);
alter table public.roof_intelligence_reports add column tenant_id uuid references public.tenant(id);
alter table public.roof_intelligence_reports add column report_folder_id uuid;
alter table public.roof_intelligence_report_revisions add column tenant_id uuid references public.tenant(id);
alter table public.roof_intelligence_report_assets add column tenant_id uuid references public.tenant(id);
alter table public.roof_intelligence_notifications add column tenant_id uuid references public.tenant(id);
alter table public.roof_intelligence_report_edit_requests add column tenant_id uuid references public.tenant(id);
alter table public.roof_intelligence_processing_feedback add column tenant_id uuid references public.tenant(id);
alter table public.roof_intelligence_property_overrides add column tenant_id uuid references public.tenant(id);

update public.contact set tenant_id = '00000000-0000-4000-8000-000000000001';
update public.organization set tenant_id = '00000000-0000-4000-8000-000000000001';
update public.organization_contact set tenant_id = '00000000-0000-4000-8000-000000000001';
update public.property_management_companies set tenant_id = '00000000-0000-4000-8000-000000000001';
update public.property_management_contacts set tenant_id = '00000000-0000-4000-8000-000000000001';
update public.proposal set tenant_id = '00000000-0000-4000-8000-000000000001';
update public.proposal_contact set tenant_id = '00000000-0000-4000-8000-000000000001';
update public.roof_intelligence_jobs set tenant_id = '00000000-0000-4000-8000-000000000001';
update public.roof_intelligence_job_items set tenant_id = '00000000-0000-4000-8000-000000000001';
update public.roof_intelligence_reports set tenant_id = '00000000-0000-4000-8000-000000000001';
update public.roof_intelligence_reports
set report_folder_id = '00000000-0000-4000-8000-000000000101';
update public.roof_intelligence_report_revisions set tenant_id = '00000000-0000-4000-8000-000000000001';
update public.roof_intelligence_report_assets set tenant_id = '00000000-0000-4000-8000-000000000001';
update public.roof_intelligence_notifications set tenant_id = '00000000-0000-4000-8000-000000000001';
update public.roof_intelligence_report_edit_requests set tenant_id = '00000000-0000-4000-8000-000000000001';
update public.roof_intelligence_processing_feedback set tenant_id = '00000000-0000-4000-8000-000000000001';
update public.roof_intelligence_property_overrides set tenant_id = '00000000-0000-4000-8000-000000000001';

alter table public.contact alter column tenant_id set not null;
alter table public.organization alter column tenant_id set not null;
alter table public.organization_contact alter column tenant_id set not null;
alter table public.property_management_companies alter column tenant_id set not null;
alter table public.property_management_contacts alter column tenant_id set not null;
alter table public.proposal alter column tenant_id set not null;
alter table public.proposal_contact alter column tenant_id set not null;
alter table public.roof_intelligence_jobs alter column tenant_id set not null;
alter table public.roof_intelligence_job_items alter column tenant_id set not null;
alter table public.roof_intelligence_reports alter column tenant_id set not null;
alter table public.roof_intelligence_reports alter column report_folder_id set not null;
alter table public.roof_intelligence_report_revisions alter column tenant_id set not null;
alter table public.roof_intelligence_report_assets alter column tenant_id set not null;
alter table public.roof_intelligence_notifications alter column tenant_id set not null;
alter table public.roof_intelligence_report_edit_requests alter column tenant_id set not null;
alter table public.roof_intelligence_processing_feedback alter column tenant_id set not null;
alter table public.roof_intelligence_property_overrides alter column tenant_id set not null;

alter table public.roof_intelligence_reports
  add constraint roof_intelligence_reports_tenant_folder_fkey
  foreign key (tenant_id, report_folder_id)
  references public.report_folder(tenant_id, id) on delete restrict;

-- Tenant-scoped uniqueness replaces global uniqueness where different companies
-- may legitimately have the same customer, contact, source row, or property override.
alter table public.organization drop constraint organization_normalized_name_key;
alter table public.organization add constraint organization_tenant_normalized_name_key
  unique (tenant_id, normalized_name);
drop index contact_linkedin_url_key;
create unique index contact_tenant_linkedin_url_key
  on public.contact (tenant_id, lower(btrim(linkedin_url)))
  where linkedin_url is not null and btrim(linkedin_url) <> '';
alter table public.proposal drop constraint proposal_source_name_source_row_number_key;
alter table public.proposal add constraint proposal_tenant_source_row_key
  unique (tenant_id, source_name, source_row_number);
drop index roof_intelligence_property_overrides_active_key;
create unique index roof_intelligence_property_overrides_tenant_active_key
  on public.roof_intelligence_property_overrides (tenant_id, property_id, field_name)
  where revoked_at is null;

-- Tenant-first indexes support both RLS checks and normal list screens.
create index contact_tenant_name_idx on public.contact (tenant_id, normalized_name);
create index organization_tenant_active_name_idx on public.organization (tenant_id, is_active, normalized_name);
create index organization_contact_tenant_current_idx on public.organization_contact (tenant_id, is_current, normalized_email);
create index proposal_tenant_status_sent_idx on public.proposal (tenant_id, status, proposal_sent_date desc);
create index roof_jobs_tenant_status_idx on public.roof_intelligence_jobs (tenant_id, status, queued_at);
create index roof_job_items_tenant_job_idx on public.roof_intelligence_job_items (tenant_id, job_id, status);
create index roof_reports_tenant_created_idx on public.roof_intelligence_reports (tenant_id, created_at desc);
create index roof_revisions_tenant_report_idx on public.roof_intelligence_report_revisions (tenant_id, report_id, revision_number desc);
create index roof_assets_tenant_revision_idx on public.roof_intelligence_report_assets (tenant_id, revision_id);
create index roof_notifications_tenant_recipient_idx on public.roof_intelligence_notifications (tenant_id, recipient_id, is_read, created_at desc);
create index roof_edit_requests_tenant_status_idx on public.roof_intelligence_report_edit_requests (tenant_id, status, created_at);
create index roof_feedback_tenant_status_idx on public.roof_intelligence_processing_feedback (tenant_id, status, created_at);

-- The app always supplies tenant_id. These triggers reject accidental
-- cross-tenant child links, including writes made by the trusted worker.
create or replace function private.enforce_tenant_parent()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  parent_tenant uuid;
begin
  execute format('select tenant_id from %I.%I where id = $1', tg_argv[0], tg_argv[1])
    into parent_tenant using (to_jsonb(new) ->> tg_argv[2])::uuid;
  if parent_tenant is null or parent_tenant <> new.tenant_id then
    raise exception 'Cross-tenant relationship is not allowed';
  end if;
  return new;
end;
$$;

create or replace function private.set_tenant_from_parent()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  parent_tenant uuid;
begin
  execute format('select tenant_id from %I.%I where id = $1', tg_argv[0], tg_argv[1])
    into parent_tenant using (to_jsonb(new) ->> tg_argv[2])::uuid;
  if parent_tenant is null then
    raise exception 'The tenant-owning parent record was not found';
  end if;
  if new.tenant_id is not null and new.tenant_id <> parent_tenant then
    raise exception 'Cross-tenant relationship is not allowed';
  end if;
  new.tenant_id := parent_tenant;
  return new;
end;
$$;

create or replace function private.set_job_tenant()
returns trigger
language plpgsql
set search_path = ''
as $$
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
    raise exception 'A trusted tenant context is required to create a Roof Intelligence job';
  end if;
  new.tenant_id := derived_tenant;
  return new;
end;
$$;

create or replace function private.set_report_tenant_and_folder()
returns trigger
language plpgsql
set search_path = ''
as $$
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
end;
$$;

create or replace function private.validate_tenant_storage_path()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  revision_report_id uuid;
  folder_id uuid;
  expected_prefix text;
begin
  select revision.report_id, report.report_folder_id
    into revision_report_id, folder_id
  from public.roof_intelligence_report_revisions revision
  join public.roof_intelligence_reports report on report.id = revision.report_id
  where revision.id = new.revision_id and revision.tenant_id = new.tenant_id;
  expected_prefix := new.tenant_id::text || '/folders/' || folder_id::text ||
    '/reports/' || revision_report_id::text || '/revisions/';
  if new.storage_path not like expected_prefix || '%' then
    raise exception 'Storage path is outside the report tenant namespace';
  end if;
  return new;
end;
$$;

create or replace function private.set_notification_tenant()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  derived_tenant uuid;
begin
  if new.report_id is not null then
    select tenant_id into derived_tenant from public.roof_intelligence_reports where id = new.report_id;
  elsif new.job_id is not null then
    select tenant_id into derived_tenant from public.roof_intelligence_jobs where id = new.job_id;
  end if;
  if derived_tenant is null or (new.tenant_id is not null and new.tenant_id <> derived_tenant) then
    raise exception 'A notification must use the tenant of its job or report';
  end if;
  new.tenant_id := derived_tenant;
  return new;
end;
$$;

create or replace function private.validate_edit_request_actor()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if (select auth.uid()) is not null and (
    new.requested_by <> (select auth.uid())
    or not private.user_has_tenant_access(new.tenant_id)
  ) then
    raise exception 'The report is outside the authenticated tenant';
  end if;
  return new;
end;
$$;

create trigger a_roof_job_set_tenant
before insert or update on public.roof_intelligence_jobs for each row
execute function private.set_job_tenant();
create trigger a_roof_report_set_tenant_and_folder
before insert or update on public.roof_intelligence_reports for each row
execute function private.set_report_tenant_and_folder();
create trigger a_roof_job_item_set_tenant
before insert or update on public.roof_intelligence_job_items for each row
execute function private.set_tenant_from_parent('public', 'roof_intelligence_jobs', 'job_id');
create trigger a_roof_revision_set_tenant
before insert or update on public.roof_intelligence_report_revisions for each row
execute function private.set_tenant_from_parent('public', 'roof_intelligence_reports', 'report_id');
create trigger a_roof_asset_set_tenant
before insert or update on public.roof_intelligence_report_assets for each row
execute function private.set_tenant_from_parent('public', 'roof_intelligence_report_revisions', 'revision_id');
create trigger a_roof_edit_request_set_tenant
before insert or update on public.roof_intelligence_report_edit_requests for each row
execute function private.set_tenant_from_parent('public', 'roof_intelligence_reports', 'report_id');
create trigger b_roof_edit_request_validate_actor
before insert or update on public.roof_intelligence_report_edit_requests for each row
execute function private.validate_edit_request_actor();
create trigger a_roof_feedback_set_tenant
before insert or update on public.roof_intelligence_processing_feedback for each row
execute function private.set_tenant_from_parent('public', 'roof_intelligence_reports', 'report_id');
create trigger a_roof_override_set_tenant
before insert or update on public.roof_intelligence_property_overrides for each row
execute function private.set_tenant_from_parent('public', 'roof_intelligence_report_revisions', 'source_revision_id');
create trigger a_roof_notification_set_tenant
before insert or update on public.roof_intelligence_notifications for each row
execute function private.set_notification_tenant();
create trigger roof_asset_validate_tenant_path
before insert or update on public.roof_intelligence_report_assets for each row
execute function private.validate_tenant_storage_path();

create trigger organization_contact_contact_tenant
before insert or update on public.organization_contact for each row
execute function private.enforce_tenant_parent('public', 'contact', 'contact_id');
create trigger organization_contact_organization_tenant
before insert or update on public.organization_contact for each row
execute function private.enforce_tenant_parent('public', 'organization', 'organization_id');
create trigger proposal_contact_proposal_tenant
before insert or update on public.proposal_contact for each row
execute function private.enforce_tenant_parent('public', 'proposal', 'proposal_id');
create trigger proposal_contact_relationship_tenant
before insert or update on public.proposal_contact for each row
execute function private.enforce_tenant_parent('public', 'organization_contact', 'organization_contact_id');
create trigger roof_job_item_job_tenant
before insert or update on public.roof_intelligence_job_items for each row
execute function private.enforce_tenant_parent('public', 'roof_intelligence_jobs', 'job_id');
create trigger roof_revision_report_tenant
before insert or update on public.roof_intelligence_report_revisions for each row
execute function private.enforce_tenant_parent('public', 'roof_intelligence_reports', 'report_id');
create trigger roof_asset_revision_tenant
before insert or update on public.roof_intelligence_report_assets for each row
execute function private.enforce_tenant_parent('public', 'roof_intelligence_report_revisions', 'revision_id');
create trigger roof_edit_request_report_tenant
before insert or update on public.roof_intelligence_report_edit_requests for each row
execute function private.enforce_tenant_parent('public', 'roof_intelligence_reports', 'report_id');
create trigger roof_feedback_report_tenant
before insert or update on public.roof_intelligence_processing_feedback for each row
execute function private.enforce_tenant_parent('public', 'roof_intelligence_reports', 'report_id');

create or replace function private.user_has_tenant_access(target_tenant_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.tenant_membership membership
    join public.tenant tenant_record on tenant_record.id = membership.tenant_id
    where membership.tenant_id = target_tenant_id
      and membership.user_id = (select auth.uid())
      and membership.is_active
      and tenant_record.is_active
  );
$$;

create or replace function private.user_is_tenant_administrator(target_tenant_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.tenant_membership membership
    where membership.tenant_id = target_tenant_id
      and membership.user_id = (select auth.uid())
      and membership.is_active
      and membership.role in ('owner', 'admin')
  );
$$;

create or replace function private.user_has_tenant_role(
  target_tenant_id uuid,
  allowed_roles text[]
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.tenant_membership membership
    join public.tenant tenant_record on tenant_record.id = membership.tenant_id
    where membership.tenant_id = target_tenant_id
      and membership.user_id = (select auth.uid())
      and membership.is_active
      and tenant_record.is_active
      and membership.role = any(allowed_roles)
  );
$$;

revoke all on schema private from public, anon;
grant usage on schema private to authenticated;
revoke all on function private.user_has_tenant_access(uuid) from public, anon;
grant execute on function private.user_has_tenant_access(uuid) to authenticated;
revoke all on function private.user_is_tenant_administrator(uuid) from public, anon;
grant execute on function private.user_is_tenant_administrator(uuid) to authenticated;
revoke all on function private.user_has_tenant_role(uuid, text[]) from public, anon;
grant execute on function private.user_has_tenant_role(uuid, text[]) to authenticated;

alter table public.tenant enable row level security;
alter table public.tenant_membership enable row level security;
alter table public.report_folder enable row level security;
alter table public.tenant_settings enable row level security;
alter table public.tenant_feature_flag enable row level security;

create policy tenant_member_read on public.tenant for select to authenticated
  using (private.user_has_tenant_access(id));
create policy membership_self_read on public.tenant_membership for select to authenticated
  using (user_id = (select auth.uid()) and is_active);

-- Owners and administrators manage memberships. The desktop beta initially
-- uses a single active membership, but the data model supports more than one.
create policy membership_admin_all on public.tenant_membership for all to authenticated
  using (private.user_is_tenant_administrator(tenant_id))
  with check (private.user_is_tenant_administrator(tenant_id));

create policy report_folder_tenant_read on public.report_folder for select to authenticated
  using (private.user_has_tenant_access(tenant_id));
create policy report_folder_tenant_admin_insert on public.report_folder for insert to authenticated
  with check (private.user_is_tenant_administrator(tenant_id));
create policy report_folder_tenant_admin_update on public.report_folder for update to authenticated
  using (private.user_is_tenant_administrator(tenant_id))
  with check (private.user_is_tenant_administrator(tenant_id));
create policy tenant_settings_tenant_read on public.tenant_settings for select to authenticated
  using (private.user_has_tenant_access(tenant_id));
create policy tenant_settings_tenant_admin_update on public.tenant_settings for update to authenticated
  using (private.user_is_tenant_administrator(tenant_id))
  with check (private.user_is_tenant_administrator(tenant_id));
create policy tenant_feature_flag_tenant_read on public.tenant_feature_flag for select to authenticated
  using (private.user_has_tenant_access(tenant_id));

-- Replace the earlier broad authenticated policies with tenant isolation.
drop policy if exists roof_intelligence_jobs_authenticated_read on public.roof_intelligence_jobs;
drop policy if exists roof_intelligence_job_items_authenticated_read on public.roof_intelligence_job_items;
drop policy if exists roof_intelligence_reports_authenticated_read on public.roof_intelligence_reports;
drop policy if exists roof_intelligence_report_revisions_authenticated_read on public.roof_intelligence_report_revisions;
drop policy if exists roof_intelligence_report_assets_authenticated_read on public.roof_intelligence_report_assets;
drop policy if exists roof_intelligence_notifications_recipient_read on public.roof_intelligence_notifications;
drop policy if exists roof_intelligence_edit_requests_authenticated_read on public.roof_intelligence_report_edit_requests;
drop policy if exists roof_intelligence_processing_feedback_authenticated_read on public.roof_intelligence_processing_feedback;
drop policy if exists roof_intelligence_property_overrides_authenticated_read on public.roof_intelligence_property_overrides;

do $policies$
declare table_name text;
begin
  foreach table_name in array array[
    'contact', 'organization', 'organization_contact',
    'property_management_companies', 'property_management_contacts',
    'proposal', 'proposal_contact', 'roof_intelligence_jobs',
    'roof_intelligence_job_items', 'roof_intelligence_reports',
    'roof_intelligence_report_revisions', 'roof_intelligence_report_assets',
    'roof_intelligence_notifications', 'roof_intelligence_report_edit_requests',
    'roof_intelligence_processing_feedback', 'roof_intelligence_property_overrides'
  ]
  loop
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
      'grant select, insert, update, delete on table public.%I to authenticated',
      table_name
    );
  end loop;
end
$policies$;

grant select on public.tenant, public.tenant_membership to authenticated;
grant select, insert, update, delete on public.report_folder, public.tenant_settings to authenticated;
grant select on public.tenant_feature_flag to authenticated;

-- Service-role privileges are explicit for the protected PilotPoint worker.
-- RLS is bypassed by that role, so cross-tenant triggers and trusted-parent
-- derivation remain the worker's database-level safety net.
grant select, insert, update, delete on
  public.tenant,
  public.tenant_membership,
  public.report_folder,
  public.tenant_settings,
  public.tenant_feature_flag,
  public.contact,
  public.organization,
  public.organization_contact,
  public.property_management_companies,
  public.property_management_contacts,
  public.proposal,
  public.proposal_contact,
  public.roof_intelligence_properties,
  public.roof_intelligence_jobs,
  public.roof_intelligence_job_items,
  public.roof_intelligence_reports,
  public.roof_intelligence_report_revisions,
  public.roof_intelligence_report_assets,
  public.roof_intelligence_notifications,
  public.roof_intelligence_report_edit_requests,
  public.roof_intelligence_processing_feedback,
  public.roof_intelligence_property_overrides
to service_role;

-- One private bucket can safely serve every tenant because the immutable UUID
-- is the first path component and Storage applies the same membership check.
create policy tenant_storage_read on storage.objects for select to authenticated
  using (
    bucket_id in ('roof-intelligence-reports', 'roof-intelligence-images')
    and exists (
      select 1 from public.tenant_membership membership
      where membership.user_id = (select auth.uid())
        and membership.is_active
        and membership.tenant_id::text = (storage.foldername(name))[1]
    )
  );
create policy tenant_storage_insert on storage.objects for insert to authenticated
  with check (
    bucket_id in ('roof-intelligence-reports', 'roof-intelligence-images')
    and exists (
      select 1 from public.tenant_membership membership
      where membership.user_id = (select auth.uid())
        and membership.is_active
        and membership.tenant_id::text = (storage.foldername(name))[1]
    )
  );
create policy tenant_storage_update on storage.objects for update to authenticated
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

comment on table public.tenant is 'Licensed company boundary for all tenant-owned PCS and PilotPoint data.';
comment on table public.tenant_feature_flag is 'Per-tenant product entitlements and optional capabilities; multi-tenancy itself is not feature flagged.';
comment on table public.report_folder is 'Tenant-controlled logical report destinations. Storage object paths use immutable folder and tenant UUIDs.';
comment on column public.tenant_settings.company_configuration is 'Typed application configuration will be layered over this tenant-owned JSON object; code constants remain fallback defaults during migration.';

commit;
