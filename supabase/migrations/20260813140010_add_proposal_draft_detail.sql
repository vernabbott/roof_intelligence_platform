alter table public.proposal
  add column if not exists draft_detail jsonb not null default '{}'::jsonb
  check (jsonb_typeof(draft_detail) = 'object');

comment on column public.proposal.draft_detail is
  'Temporary proposal-detail form snapshot used before proposal files are created; tenant access is inherited from proposal RLS.';
