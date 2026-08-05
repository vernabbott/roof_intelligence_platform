begin;

-- A proposal owns customer and project identity. Proposal tracking is a
-- one-to-one extension containing only lifecycle and assignment fields.
alter table public.proposal
  add constraint proposal_tenant_id_key unique (tenant_id, id);

create table public.proposal_tracking (
  proposal_id uuid primary key,
  tenant_id uuid not null references public.tenant(id),
  lead_source text,
  submitted_by text,
  estimated_by text,
  estimate_completed_date date,
  proposal_sent_date date,
  follow_up_date date,
  response_notes text,
  status text not null default 'draft' check (
    status in ('draft', 'sent', 'under_contract', 'dead')
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
  proposal_id, tenant_id, lead_source, submitted_by, estimated_by,
  estimate_completed_date, proposal_sent_date, follow_up_date,
  response_notes, status, source_name, source_row_number, created_at, updated_at
)
select
  id, tenant_id, lead_source, submitted_by, estimated_by,
  estimate_completed_date, proposal_sent_date, follow_up_date,
  response_notes, status, source_name, source_row_number, created_at, updated_at
from public.proposal;

do $validation$
declare
  proposal_count bigint;
  tracking_count bigint;
begin
  select count(*) into proposal_count from public.proposal;
  select count(*) into tracking_count from public.proposal_tracking;
  if proposal_count <> tracking_count then
    raise exception 'Proposal tracking migration lost rows: proposals %, tracking %',
      proposal_count, tracking_count;
  end if;
end
$validation$;

drop index if exists public.proposal_follow_up_queue_idx;
drop index if exists public.proposal_tenant_status_sent_idx;
alter table public.proposal drop constraint proposal_tenant_source_row_key;

alter table public.proposal
  drop column lead_source,
  drop column submitted_by,
  drop column estimated_by,
  drop column estimate_completed_date,
  drop column proposal_sent_date,
  drop column follow_up_date,
  drop column response_notes,
  drop column status,
  drop column source_name,
  drop column source_row_number;

create index proposal_tracking_tenant_status_sent_idx
  on public.proposal_tracking (tenant_id, status, proposal_sent_date desc);
create index proposal_tracking_tenant_follow_up_queue_idx
  on public.proposal_tracking (tenant_id, proposal_sent_date, follow_up_date)
  where proposal_sent_date is not null and follow_up_date is null;

create trigger proposal_tracking_set_updated_at
before update on public.proposal_tracking
for each row execute function public.set_property_management_updated_at();

comment on table public.proposal is
  'Proposal customer and project identity. Lifecycle tracking is stored one-to-one in proposal_tracking.';
comment on table public.proposal_tracking is
  'One-to-one lifecycle, assignment, response, and import metadata for a proposal.';
comment on column public.proposal_tracking.proposal_id is
  'Both the primary key and foreign key, enforcing at most one tracking row per proposal.';
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
grant select, insert, update, delete on public.proposal_tracking to service_role;

commit;
