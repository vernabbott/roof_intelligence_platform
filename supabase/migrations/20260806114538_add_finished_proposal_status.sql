begin;

alter table public.proposal_tracking
  drop constraint proposal_tracking_status_check;

alter table public.proposal_tracking
  add constraint proposal_tracking_status_check
  check (status in ('draft', 'sent', 'under_contract', 'finished', 'dead'));

comment on column public.proposal_tracking.status is
  'Proposal lifecycle: draft, sent, under contract, finished, or dead.';

notify pgrst, 'reload schema';

commit;
