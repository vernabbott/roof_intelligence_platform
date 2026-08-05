-- Consolidated local-development baseline for the current PCS contact model.
-- This represents the final production shape after the August 2026 contact
-- migrations, without copying any production contact or organization data.

begin;

create extension if not exists pgcrypto;

create table if not exists public.contact (
  id uuid primary key default gen_random_uuid(),
  full_name text not null constraint contact_full_name_not_blank
    check (btrim(full_name) <> ''),
  normalized_name text generated always as (
    lower(regexp_replace(btrim(full_name), '[[:space:]]+', ' ', 'g'))
  ) stored,
  first_name text,
  last_name text,
  linkedin_url text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.organization (
  id uuid primary key default gen_random_uuid(),
  name text not null constraint organization_name_not_blank
    check (btrim(name) <> ''),
  normalized_name text generated always as (
    lower(regexp_replace(btrim(name), '[[:space:]]+', ' ', 'g'))
  ) stored,
  organization_type text not null default 'Other'
    constraint organization_type_not_blank check (btrim(organization_type) <> ''),
  legal_name text,
  website text,
  email_domain text,
  main_email text constraint organization_main_email_format
    check (main_email is null or position('@' in main_email) > 1),
  main_phone text,
  main_office_address_line_1 text,
  main_office_address_line_2 text,
  main_office_city text,
  main_office_state text constraint organization_state_format
    check (main_office_state is null or char_length(btrim(main_office_state)) = 2),
  main_office_zip_code text,
  dora_license_number text,
  dora_license_status text,
  source_name text,
  source_url text,
  is_active boolean not null default true,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint organization_normalized_name_key unique (normalized_name)
);

create table if not exists public.organization_contact (
  id uuid primary key default gen_random_uuid(),
  contact_id uuid not null
    constraint organization_contact_contact_id_fkey
    references public.contact(id) on delete restrict,
  organization_id uuid not null
    constraint organization_contact_organization_id_fkey
    references public.organization(id) on delete restrict,
  title text,
  business_email text constraint organization_contact_email_format
    check (business_email is null or position('@' in business_email) > 1),
  normalized_email text generated always as (
    nullif(lower(btrim(business_email)), '')
  ) stored,
  business_phone text,
  mobile_phone text,
  branch_address_line_1 text,
  branch_address_line_2 text,
  branch_city text,
  branch_state text constraint organization_contact_state_format
    check (branch_state is null or char_length(btrim(branch_state)) = 2),
  branch_zip_code text,
  source_name text,
  source_url text,
  is_current boolean not null default true,
  do_not_contact boolean not null default false,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists contact_normalized_name_idx
  on public.contact (normalized_name);
create unique index if not exists contact_linkedin_url_key
  on public.contact (lower(btrim(linkedin_url)))
  where linkedin_url is not null and btrim(linkedin_url) <> '';
create index if not exists organization_active_name_idx
  on public.organization (is_active, normalized_name);
create index if not exists organization_email_domain_idx
  on public.organization (lower(email_domain)) where email_domain is not null;
create index if not exists organization_type_idx
  on public.organization (organization_type);
create index if not exists organization_contact_contact_id_idx
  on public.organization_contact (contact_id);
create index if not exists organization_contact_organization_id_idx
  on public.organization_contact (organization_id);
create index if not exists organization_contact_current_email_idx
  on public.organization_contact (normalized_email)
  where is_current and normalized_email is not null;
create unique index if not exists organization_contact_one_current_per_contact_key
  on public.organization_contact (contact_id) where is_current;

drop trigger if exists contact_set_updated_at on public.contact;
create trigger contact_set_updated_at before update on public.contact
for each row execute function public.set_property_management_updated_at();
drop trigger if exists organization_set_updated_at on public.organization;
create trigger organization_set_updated_at before update on public.organization
for each row execute function public.set_property_management_updated_at();
drop trigger if exists organization_contact_set_updated_at on public.organization_contact;
create trigger organization_contact_set_updated_at before update on public.organization_contact
for each row execute function public.set_property_management_updated_at();

comment on table public.contact is
  'Canonical identity for a person. Organization-specific details are stored in organization_contact.';
comment on table public.organization is
  'Organizations associated with contacts, including property managers, roofers, owners, distributors, vendors, and others.';
comment on table public.organization_contact is
  'A contact relationship with one organization, including company-specific communication details and history.';

alter table public.contact enable row level security;
alter table public.organization enable row level security;
alter table public.organization_contact enable row level security;

revoke all on table public.contact from anon, authenticated;
revoke all on table public.organization from anon, authenticated;
revoke all on table public.organization_contact from anon, authenticated;
grant select, insert, update, delete on table public.contact to service_role;
grant select, insert, update, delete on table public.organization to service_role;
grant select, insert, update, delete on table public.organization_contact to service_role;

commit;
