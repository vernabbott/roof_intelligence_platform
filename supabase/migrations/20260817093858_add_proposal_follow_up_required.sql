begin;

alter table public.proposal_tracking
  add column follow_up_required boolean not null default true;

comment on column public.proposal_tracking.follow_up_required is
  'True when a sent proposal should remain eligible for the follow-up queue; false when no follow-up is intended.';

drop index if exists public.proposal_tracking_tenant_follow_up_queue_idx;
create index proposal_tracking_tenant_follow_up_queue_idx
  on public.proposal_tracking (tenant_id, proposal_sent_date, follow_up_date)
  where proposal_sent_date is not null
    and follow_up_date is null
    and follow_up_required;

notify pgrst, 'reload schema';

commit;
