-- Opt-in, human-reviewed feedback queue for improving future roof processing.

begin;

alter table public.roof_intelligence_report_edit_requests
  add column submit_for_future_processing boolean not null default false;

create table public.roof_intelligence_processing_feedback (
  id uuid primary key default gen_random_uuid(),
  edit_request_id uuid not null unique
    references public.roof_intelligence_report_edit_requests(id)
    on update cascade
    on delete restrict,
  report_id uuid not null
    references public.roof_intelligence_reports(id)
    on update cascade
    on delete restrict,
  property_id uuid not null
    references public.roof_intelligence_properties(id)
    on update cascade
    on delete restrict,
  parent_revision_id uuid not null
    references public.roof_intelligence_report_revisions(id)
    on update cascade
    on delete restrict,
  completed_revision_id uuid
    references public.roof_intelligence_report_revisions(id)
    on update cascade
    on delete restrict,
  requested_by uuid not null references auth.users(id) on delete restrict,
  comment text not null check (char_length(btrim(comment)) >= 10),
  before_values jsonb not null check (jsonb_typeof(before_values) = 'object'),
  corrected_values jsonb not null check (
    jsonb_typeof(corrected_values) = 'object'
    and corrected_values <> '{}'::jsonb
  ),
  learning_scopes text[] not null check (cardinality(learning_scopes) > 0),
  property_identity jsonb not null check (jsonb_typeof(property_identity) = 'object'),
  imagery_identity jsonb not null check (jsonb_typeof(imagery_identity) = 'object'),
  status text not null default 'pending_review' check (
    status in ('pending_review', 'approved', 'rejected', 'applied')
  ),
  reviewed_by_label text,
  review_note text,
  reviewed_at timestamptz,
  applied_workflow_version text,
  applied_artifacts jsonb,
  applied_by_label text,
  applied_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (
    (
      status = 'pending_review'
      and reviewed_at is null
      and reviewed_by_label is null
      and review_note is null
    )
    or (
      status in ('approved', 'rejected', 'applied')
      and reviewed_at is not null
      and reviewed_by_label is not null
      and review_note is not null
      and char_length(btrim(reviewed_by_label)) > 0
      and char_length(btrim(review_note)) >= 10
    )
  ),
  check (
    (
      status <> 'applied'
      and applied_at is null
      and applied_by_label is null
      and applied_workflow_version is null
      and applied_artifacts is null
    )
    or (
      status = 'applied'
      and applied_at is not null
      and applied_by_label is not null
      and applied_workflow_version is not null
      and applied_artifacts is not null
      and char_length(btrim(applied_by_label)) > 0
      and char_length(btrim(applied_workflow_version)) > 0
      and jsonb_typeof(applied_artifacts) = 'array'
      and jsonb_array_length(applied_artifacts) > 0
    )
  )
);

create index roof_intelligence_processing_feedback_status_idx
  on public.roof_intelligence_processing_feedback (status, created_at);
create index roof_intelligence_processing_feedback_property_idx
  on public.roof_intelligence_processing_feedback (property_id, created_at desc);

create trigger roof_intelligence_processing_feedback_set_updated_at
before update on public.roof_intelligence_processing_feedback
for each row execute function public.set_roof_intelligence_updated_at();

create or replace function public.queue_roof_intelligence_processing_feedback()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  parent public.roof_intelligence_report_revisions%rowtype;
  report_property_id uuid;
  property_record public.roof_intelligence_properties%rowtype;
  scopes text[] := array[]::text[];
  before_data jsonb := '{}'::jsonb;
begin
  if not new.submit_for_future_processing then
    return new;
  end if;

  select * into parent
    from public.roof_intelligence_report_revisions
    where id = new.parent_revision_id;
  select property_id into report_property_id
    from public.roof_intelligence_reports
    where id = new.report_id;
  select * into property_record
    from public.roof_intelligence_properties
    where id = report_property_id;

  if new.edit_patch ? 'roof_area_sqft' then
    before_data := before_data || jsonb_build_object('roof_area_sqft', parent.roof_area_sqft);
    scopes := array_append(scopes, 'property_measurement');
  end if;
  if new.edit_patch ? 'roof_type' then
    before_data := before_data || jsonb_build_object('roof_type', parent.roof_type);
    scopes := array_append(scopes, 'material_reference');
  end if;
  if new.edit_patch ? 'roof_system' then
    before_data := before_data || jsonb_build_object('roof_system', parent.roof_system);
    scopes := array_append(scopes, 'roof_configuration');
  end if;
  if new.edit_patch ? 'roof_condition_score' then
    before_data := before_data || jsonb_build_object('roof_condition_score', parent.roof_condition_score);
    scopes := array_append(scopes, 'condition_scoring');
  end if;
  if new.edit_patch ? 'report_summary' then
    before_data := before_data || jsonb_build_object('report_summary', parent.report_summary);
    scopes := array_append(scopes, 'narrative_guidance');
  end if;
  if new.edit_patch ? 'recommendation' then
    before_data := before_data || jsonb_build_object('recommendation', parent.recommendation);
    scopes := array_append(scopes, 'recommendation_guidance');
  end if;

  insert into public.roof_intelligence_processing_feedback (
    edit_request_id, report_id, property_id, parent_revision_id,
    requested_by, comment, before_values, corrected_values, learning_scopes,
    property_identity, imagery_identity
  ) values (
    new.id, new.report_id, report_property_id, new.parent_revision_id,
    new.requested_by, new.change_reason, before_data, new.edit_patch, scopes,
    jsonb_build_object(
      'property_id', property_record.id,
      'canonical_key', property_record.canonical_key,
      'address', property_record.address,
      'city', property_record.city,
      'state', property_record.state,
      'zip_code', property_record.zip_code,
      'county', property_record.county,
      'parcel_number', property_record.parcel_number
    ),
    jsonb_build_object(
      'source', parent.source_snapshot -> 'imagery' ->> 'source',
      'capture_date', parent.source_snapshot -> 'imagery' ->> 'capture_date',
      'report_image_asset_id', parent.source_snapshot -> 'imagery' ->> 'report_image_asset_id',
      'reference_workflow', parent.analysis_snapshot -> 'reference_workflow'
    )
  )
  on conflict (edit_request_id) do nothing;
  return new;
end;
$$;

create trigger roof_intelligence_edit_request_queue_processing_feedback
after insert or update of submit_for_future_processing
on public.roof_intelligence_report_edit_requests
for each row execute function public.queue_roof_intelligence_processing_feedback();

create or replace function public.link_completed_revision_to_processing_feedback()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.status = 'completed' and new.completed_revision_id is not null then
    update public.roof_intelligence_processing_feedback
    set completed_revision_id = new.completed_revision_id
    where edit_request_id = new.id;
  end if;
  return new;
end;
$$;

create trigger roof_intelligence_edit_request_link_feedback_revision
after update of status, completed_revision_id
on public.roof_intelligence_report_edit_requests
for each row execute function public.link_completed_revision_to_processing_feedback();

create or replace function public.request_roof_intelligence_report_edit(
  target_report_id uuid,
  target_parent_revision_id uuid,
  requested_edit_patch jsonb,
  requested_change_reason text,
  apply_to_future boolean,
  request_key text,
  submit_for_learning boolean
)
returns table (edit_request_id uuid, revision_job_id uuid)
language plpgsql
security definer
set search_path = public
as $$
declare
  created_edit_request_id uuid;
  created_revision_job_id uuid;
begin
  select result.edit_request_id, result.revision_job_id
    into created_edit_request_id, created_revision_job_id
    from public.request_roof_intelligence_report_edit(
      target_report_id,
      target_parent_revision_id,
      requested_edit_patch,
      requested_change_reason,
      apply_to_future,
      request_key
    ) result;

  update public.roof_intelligence_report_edit_requests
  set submit_for_future_processing = submit_for_learning
  where id = created_edit_request_id;

  return query select created_edit_request_id, created_revision_job_id;
end;
$$;

revoke all on function public.request_roof_intelligence_report_edit(
  uuid, uuid, jsonb, text, boolean, text, boolean
) from public, anon;
grant execute on function public.request_roof_intelligence_report_edit(
  uuid, uuid, jsonb, text, boolean, text, boolean
) to authenticated;

create or replace function public.review_roof_intelligence_processing_feedback(
  target_feedback_id uuid,
  decision text,
  reviewer_label text,
  decision_note text
)
returns public.roof_intelligence_processing_feedback
language plpgsql
security definer
set search_path = public
as $$
declare
  reviewed public.roof_intelligence_processing_feedback%rowtype;
begin
  if decision not in ('approved', 'rejected') then
    raise exception 'Decision must be approved or rejected';
  end if;
  if char_length(btrim(coalesce(reviewer_label, ''))) = 0
     or char_length(btrim(coalesce(decision_note, ''))) < 10 then
    raise exception 'Reviewer and a substantive decision note are required';
  end if;
  update public.roof_intelligence_processing_feedback
  set status = decision,
      reviewed_by_label = btrim(reviewer_label),
      review_note = btrim(decision_note),
      reviewed_at = now()
  where id = target_feedback_id and status = 'pending_review'
  returning * into reviewed;
  if reviewed.id is null then
    raise exception 'Pending processing feedback was not found';
  end if;
  return reviewed;
end;
$$;

revoke all on function public.review_roof_intelligence_processing_feedback(uuid, text, text, text)
  from public, anon, authenticated;
grant execute on function public.review_roof_intelligence_processing_feedback(uuid, text, text, text)
  to service_role;

create or replace function public.mark_roof_intelligence_processing_feedback_applied(
  target_feedback_id uuid,
  workflow_version text,
  artifacts jsonb,
  applied_by text
)
returns public.roof_intelligence_processing_feedback
language plpgsql
security definer
set search_path = public
as $$
declare
  applied public.roof_intelligence_processing_feedback%rowtype;
begin
  if char_length(btrim(coalesce(workflow_version, ''))) = 0
     or jsonb_typeof(artifacts) <> 'array'
     or jsonb_array_length(artifacts) = 0
     or char_length(btrim(coalesce(applied_by, ''))) = 0 then
    raise exception 'Workflow version, applied artifacts, and applied-by identity are required';
  end if;
  update public.roof_intelligence_processing_feedback
  set status = 'applied',
      applied_workflow_version = btrim(workflow_version),
      applied_artifacts = artifacts,
      applied_by_label = btrim(applied_by),
      applied_at = now()
  where id = target_feedback_id and status = 'approved'
  returning * into applied;
  if applied.id is null then
    raise exception 'Approved processing feedback was not found';
  end if;
  return applied;
end;
$$;

revoke all on function public.mark_roof_intelligence_processing_feedback_applied(uuid, text, jsonb, text)
  from public, anon, authenticated;
grant execute on function public.mark_roof_intelligence_processing_feedback_applied(uuid, text, jsonb, text)
  to service_role;

alter table public.roof_intelligence_processing_feedback enable row level security;

create policy roof_intelligence_processing_feedback_authenticated_read
  on public.roof_intelligence_processing_feedback for select to authenticated using (true);

comment on table public.roof_intelligence_processing_feedback is
  'Opt-in report corrections awaiting human review and durable application to references, guides, known-building logic, or evaluation cases.';
comment on column public.roof_intelligence_processing_feedback.status is
  'Pending and approved feedback does not affect report processing. Only applied feedback with named workflow artifacts may influence future reports.';

commit;
