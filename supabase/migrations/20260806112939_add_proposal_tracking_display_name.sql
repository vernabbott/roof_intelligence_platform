begin;

alter table public.proposal_tracking
  add column proposal_display_name text;

update public.proposal_tracking as tracking
set proposal_display_name = proposal.display_name
from public.proposal as proposal
where proposal.tenant_id = tracking.tenant_id
  and proposal.id = tracking.proposal_id;

alter table public.proposal_tracking
  alter column proposal_display_name set not null;

create or replace function public.set_proposal_tracking_display_name()
returns trigger
language plpgsql
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

create trigger proposal_tracking_set_display_name
before insert or update on public.proposal_tracking
for each row execute function public.set_proposal_tracking_display_name();

create or replace function public.sync_proposal_display_name_to_tracking()
returns trigger
language plpgsql
set search_path = ''
as $function$
begin
  update public.proposal_tracking
  set proposal_display_name = new.display_name
  where tenant_id = new.tenant_id
    and proposal_id = new.id;

  return new;
end
$function$;

create trigger proposal_sync_display_name_to_tracking
after update of customer_name, project_street_address on public.proposal
for each row
when (old.display_name is distinct from new.display_name)
execute function public.sync_proposal_display_name_to_tracking();

comment on column public.proposal_tracking.proposal_display_name is
  'Troubleshooting copy of proposal.display_name, maintained automatically as Customer - Street Address.';

commit;
