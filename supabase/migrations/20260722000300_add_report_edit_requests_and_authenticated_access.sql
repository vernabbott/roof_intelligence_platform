-- Authenticated PCS review/edit queue for immutable Roof Intelligence revisions.
-- This remains dormant until PCS and PilotPoint enable their corresponding flags.

begin;

alter table public.roof_intelligence_jobs
  drop constraint roof_intelligence_jobs_job_type_check;
alter table public.roof_intelligence_jobs
  add constraint roof_intelligence_jobs_job_type_check check (
    job_type in ('individual_address', 'area_selection', 'zip_batch', 'report_revision')
  );

create table public.roof_intelligence_report_edit_requests (
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null
    references public.roof_intelligence_reports(id)
    on update cascade
    on delete restrict,
  parent_revision_id uuid not null
    references public.roof_intelligence_report_revisions(id)
    on update cascade
    on delete restrict,
  job_id uuid not null unique
    references public.roof_intelligence_jobs(id)
    on update cascade
    on delete restrict,
  requested_by uuid not null references auth.users(id) on delete restrict,
  edit_patch jsonb not null check (
    jsonb_typeof(edit_patch) = 'object'
    and edit_patch <> '{}'::jsonb
    and edit_patch - array[
      'roof_area_sqft', 'roof_type', 'roof_system', 'roof_condition_score',
      'report_summary', 'recommendation'
    ]::text[] = '{}'::jsonb
    and (not edit_patch ? 'roof_area_sqft' or (
      jsonb_typeof(edit_patch -> 'roof_area_sqft') = 'number'
      and (edit_patch ->> 'roof_area_sqft')::numeric >= 0
    ))
    and (not edit_patch ? 'roof_condition_score' or (
      jsonb_typeof(edit_patch -> 'roof_condition_score') = 'number'
      and (edit_patch ->> 'roof_condition_score')::numeric between 0 and 100
    ))
    and (not edit_patch ? 'roof_type' or jsonb_typeof(edit_patch -> 'roof_type') = 'string')
    and (not edit_patch ? 'roof_system' or jsonb_typeof(edit_patch -> 'roof_system') = 'string')
    and (not edit_patch ? 'report_summary' or jsonb_typeof(edit_patch -> 'report_summary') = 'string')
    and (not edit_patch ? 'recommendation' or jsonb_typeof(edit_patch -> 'recommendation') = 'string')
  ),
  change_reason text not null check (char_length(btrim(change_reason)) >= 10),
  apply_square_footage_to_future boolean not null default false,
  status text not null default 'queued' check (
    status in ('queued', 'generating', 'completed', 'failed', 'cancelled')
  ),
  completed_revision_id uuid
    references public.roof_intelligence_report_revisions(id)
    on update cascade
    on delete restrict,
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  check (not apply_square_footage_to_future or edit_patch ? 'roof_area_sqft'),
  check (
    (status = 'completed' and completed_revision_id is not null and completed_at is not null)
    or (status <> 'completed' and completed_revision_id is null and completed_at is null)
  )
);

create index roof_intelligence_report_edit_requests_report_idx
  on public.roof_intelligence_report_edit_requests (report_id, created_at desc);
create index roof_intelligence_report_edit_requests_status_idx
  on public.roof_intelligence_report_edit_requests (status, created_at)
  where status in ('queued', 'generating');

create trigger roof_intelligence_report_edit_requests_set_updated_at
before update on public.roof_intelligence_report_edit_requests
for each row execute function public.set_roof_intelligence_updated_at();

create or replace function public.validate_roof_intelligence_edit_request_lineage()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  parent_report_id uuid;
  parent_status text;
  report_status text;
  report_retention_expires_at timestamptz;
  newest_ready_revision_id uuid;
begin
  select revision.report_id, revision.generation_status,
         report.status, report.retention_expires_at
    into parent_report_id, parent_status, report_status, report_retention_expires_at
    from public.roof_intelligence_report_revisions revision
    join public.roof_intelligence_reports report on report.id = revision.report_id
    where revision.id = new.parent_revision_id;

  if parent_report_id is null or parent_report_id <> new.report_id then
    raise exception 'The selected parent revision does not belong to this report';
  end if;
  if parent_status <> 'ready' then
    raise exception 'Only a Ready revision can be edited';
  end if;
  if report_status <> 'active' or report_retention_expires_at <= now() then
    raise exception 'This report is no longer available for editing';
  end if;

  select id
    into newest_ready_revision_id
    from public.roof_intelligence_report_revisions
    where report_id = new.report_id and generation_status = 'ready'
    order by revision_number desc
    limit 1;
  if newest_ready_revision_id <> new.parent_revision_id then
    raise exception 'A new revision already exists; reload the report before editing';
  end if;
  return new;
end;
$$;

create trigger roof_intelligence_report_edit_requests_validate_lineage
before insert or update of report_id, parent_revision_id
on public.roof_intelligence_report_edit_requests
for each row execute function public.validate_roof_intelligence_edit_request_lineage();

create or replace function public.request_roof_intelligence_report_edit(
  target_report_id uuid,
  target_parent_revision_id uuid,
  requested_edit_patch jsonb,
  requested_change_reason text,
  apply_to_future boolean default false,
  request_key text default null
)
returns table (edit_request_id uuid, revision_job_id uuid)
language plpgsql
security definer
set search_path = public
as $$
declare
  actor_id uuid := auth.uid();
  normalized_key text;
  created_job_id uuid;
  created_request_id uuid;
begin
  if actor_id is null then
    raise exception 'Authentication is required';
  end if;
  if char_length(btrim(coalesce(requested_change_reason, ''))) < 10 then
    raise exception 'A change reason of at least 10 characters is required';
  end if;
  if requested_edit_patch is null or jsonb_typeof(requested_edit_patch) <> 'object'
     or requested_edit_patch = '{}'::jsonb then
    raise exception 'At least one report field must be changed';
  end if;

  normalized_key := case
    when nullif(btrim(request_key), '') is null then null
    else actor_id::text || ':report-edit:' || btrim(request_key)
  end;

  insert into public.roof_intelligence_jobs (
    job_type, requested_by, status, stage, input, idempotency_key
  ) values (
    'report_revision', actor_id, 'queued', 'queued',
    jsonb_build_object(
      'report_id', target_report_id,
      'parent_revision_id', target_parent_revision_id
    ),
    normalized_key
  )
  on conflict (idempotency_key) where idempotency_key is not null
  do update set idempotency_key = excluded.idempotency_key
  returning id into created_job_id;

  select id into created_request_id
    from public.roof_intelligence_report_edit_requests
    where job_id = created_job_id;
  if created_request_id is null then
    insert into public.roof_intelligence_report_edit_requests (
      report_id, parent_revision_id, job_id, requested_by, edit_patch,
      change_reason, apply_square_footage_to_future
    ) values (
      target_report_id, target_parent_revision_id, created_job_id, actor_id,
      requested_edit_patch, btrim(requested_change_reason), apply_to_future
    )
    returning id into created_request_id;
  end if;

  return query select created_request_id, created_job_id;
end;
$$;

revoke all on function public.request_roof_intelligence_report_edit(
  uuid, uuid, jsonb, text, boolean, text
) from public, anon;
grant execute on function public.request_roof_intelligence_report_edit(
  uuid, uuid, jsonb, text, boolean, text
) to authenticated;

create or replace function public.mark_roof_intelligence_notification_read(
  target_notification_id uuid
)
returns boolean
language sql
security definer
set search_path = public
as $$
  update public.roof_intelligence_notifications
  set is_read = true, read_at = coalesce(read_at, now())
  where id = target_notification_id
    and recipient_id = auth.uid()
  returning true;
$$;

revoke all on function public.mark_roof_intelligence_notification_read(uuid)
  from public, anon;
grant execute on function public.mark_roof_intelligence_notification_read(uuid)
  to authenticated;

alter table public.roof_intelligence_report_edit_requests enable row level security;

create policy roof_intelligence_properties_authenticated_read
  on public.roof_intelligence_properties for select to authenticated using (true);
create policy roof_intelligence_jobs_authenticated_read
  on public.roof_intelligence_jobs for select to authenticated using (true);
create policy roof_intelligence_job_items_authenticated_read
  on public.roof_intelligence_job_items for select to authenticated using (true);
create policy roof_intelligence_reports_authenticated_read
  on public.roof_intelligence_reports for select to authenticated using (true);
create policy roof_intelligence_report_revisions_authenticated_read
  on public.roof_intelligence_report_revisions for select to authenticated using (true);
create policy roof_intelligence_report_assets_authenticated_read
  on public.roof_intelligence_report_assets for select to authenticated using (true);
create policy roof_intelligence_property_overrides_authenticated_read
  on public.roof_intelligence_property_overrides for select to authenticated using (true);
create policy roof_intelligence_edit_requests_authenticated_read
  on public.roof_intelligence_report_edit_requests for select to authenticated using (true);
create policy roof_intelligence_county_health_authenticated_read
  on public.roof_intelligence_county_health_checks for select to authenticated using (true);
create policy roof_intelligence_notifications_recipient_read
  on public.roof_intelligence_notifications for select to authenticated
  using (recipient_id = auth.uid());

comment on table public.roof_intelligence_report_edit_requests is
  'Authenticated PCS requests for a newly generated immutable report revision. Requests never alter an existing Ready revision.';
comment on function public.request_roof_intelligence_report_edit(uuid, uuid, jsonb, text, boolean, text) is
  'Queues an idempotent report-revision job for any authenticated PCS user. PilotPoint completes it with service-role access.';

commit;
