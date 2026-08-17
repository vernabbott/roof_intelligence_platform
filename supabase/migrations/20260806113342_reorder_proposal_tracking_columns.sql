begin;

set local lock_timeout = '10s';

lock table public.proposal_tracking in access exclusive mode;
alter table public.proposal_tracking rename to proposal_tracking_previous_order;

create table public.proposal_tracking (
  proposal_id uuid not null,
  tenant_id uuid not null,
  proposal_display_name text not null,
  submitted_by text,
  estimated_by text,
  estimate_completed_date date,
  proposal_sent_date date,
  follow_up_date date,
  lead_source text,
  response_notes text,
  status text not null default 'draft',
  source_name text,
  source_row_number integer,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint proposal_tracking_reordered_pkey primary key (proposal_id),
  constraint proposal_tracking_reordered_tenant_id_fkey
    foreign key (tenant_id) references public.tenant(id),
  constraint proposal_tracking_reordered_proposal_tenant_fkey
    foreign key (tenant_id, proposal_id)
    references public.proposal(tenant_id, id) on delete cascade,
  constraint proposal_tracking_reordered_tenant_source_row_key
    unique (tenant_id, source_name, source_row_number),
  constraint proposal_tracking_reordered_source_row_number_check check (
    source_row_number is null or source_row_number >= 2
  ),
  constraint proposal_tracking_reordered_status_check check (
    status in ('draft', 'sent', 'under_contract', 'dead')
  )
);

insert into public.proposal_tracking (
  proposal_id,
  tenant_id,
  proposal_display_name,
  submitted_by,
  estimated_by,
  estimate_completed_date,
  proposal_sent_date,
  follow_up_date,
  lead_source,
  response_notes,
  status,
  source_name,
  source_row_number,
  created_at,
  updated_at
)
select
  proposal_id,
  tenant_id,
  proposal_display_name,
  submitted_by,
  estimated_by,
  estimate_completed_date,
  proposal_sent_date,
  follow_up_date,
  lead_source,
  response_notes,
  status,
  source_name,
  source_row_number,
  created_at,
  updated_at
from public.proposal_tracking_previous_order;

do $validation$
begin
  if (
    select count(*) from public.proposal_tracking
  ) <> (
    select count(*) from public.proposal_tracking_previous_order
  ) then
    raise exception 'Proposal tracking reorder changed the row count';
  end if;

  if exists (
    select 1
    from public.proposal_tracking_previous_order as previous
    full join public.proposal_tracking as reordered
      on reordered.proposal_id = previous.proposal_id
    where row(
      reordered.proposal_id,
      reordered.tenant_id,
      reordered.proposal_display_name,
      reordered.submitted_by,
      reordered.estimated_by,
      reordered.estimate_completed_date,
      reordered.proposal_sent_date,
      reordered.follow_up_date,
      reordered.lead_source,
      reordered.response_notes,
      reordered.status,
      reordered.source_name,
      reordered.source_row_number,
      reordered.created_at,
      reordered.updated_at
    ) is distinct from row(
      previous.proposal_id,
      previous.tenant_id,
      previous.proposal_display_name,
      previous.submitted_by,
      previous.estimated_by,
      previous.estimate_completed_date,
      previous.proposal_sent_date,
      previous.follow_up_date,
      previous.lead_source,
      previous.response_notes,
      previous.status,
      previous.source_name,
      previous.source_row_number,
      previous.created_at,
      previous.updated_at
    )
  ) then
    raise exception 'Proposal tracking reorder changed row data';
  end if;
end
$validation$;

drop table public.proposal_tracking_previous_order;

alter table public.proposal_tracking
  rename constraint proposal_tracking_reordered_pkey
  to proposal_tracking_pkey;
alter table public.proposal_tracking
  rename constraint proposal_tracking_reordered_tenant_id_fkey
  to proposal_tracking_tenant_id_fkey;
alter table public.proposal_tracking
  rename constraint proposal_tracking_reordered_proposal_tenant_fkey
  to proposal_tracking_proposal_tenant_fkey;
alter table public.proposal_tracking
  rename constraint proposal_tracking_reordered_tenant_source_row_key
  to proposal_tracking_tenant_source_row_key;
alter table public.proposal_tracking
  rename constraint proposal_tracking_reordered_source_row_number_check
  to proposal_tracking_source_row_number_check;
alter table public.proposal_tracking
  rename constraint proposal_tracking_reordered_status_check
  to proposal_tracking_status_check;

create index proposal_tracking_tenant_status_sent_idx
  on public.proposal_tracking (tenant_id, status, proposal_sent_date desc);
create index proposal_tracking_tenant_follow_up_queue_idx
  on public.proposal_tracking (tenant_id, proposal_sent_date, follow_up_date)
  where proposal_sent_date is not null and follow_up_date is null;

create trigger proposal_tracking_set_display_name
before insert or update on public.proposal_tracking
for each row execute function public.set_proposal_tracking_display_name();

create trigger proposal_tracking_set_updated_at
before update on public.proposal_tracking
for each row execute function public.set_property_management_updated_at();

comment on table public.proposal_tracking is
  'One-to-one lifecycle, assignment, response, and import metadata for a proposal.';
comment on column public.proposal_tracking.proposal_id is
  'Both the primary key and foreign key, enforcing at most one tracking row per proposal.';
comment on column public.proposal_tracking.proposal_display_name is
  'Troubleshooting copy of proposal.display_name, maintained automatically as Customer - Street Address.';
comment on column public.proposal_tracking.follow_up_date is
  'Follow-up activity date; it does not create a separate proposal status.';

alter table public.proposal_tracking enable row level security;
revoke all on table public.proposal_tracking from anon, authenticated;

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

grant select, insert, update, delete on public.proposal_tracking to authenticated;
grant all privileges on public.proposal_tracking to service_role;

notify pgrst, 'reload schema';

commit;
