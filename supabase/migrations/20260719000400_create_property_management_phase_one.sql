-- Phase 1 property-management account and contact schema.
--
-- This migration intentionally does not link companies to properties or
-- building footprints. Those time-dependent assignments belong in phase 2.

begin;

create extension if not exists pgcrypto;

create table if not exists public.property_management_companies (
  id uuid primary key default gen_random_uuid(),
  name text not null check (btrim(name) <> ''),
  normalized_name text generated always as (
    lower(regexp_replace(btrim(name), '[[:space:]]+', ' ', 'g'))
  ) stored,
  legal_name text,
  website text,
  email_domain text,
  main_email text check (main_email is null or position('@' in main_email) > 1),
  main_phone text,
  address_line_1 text,
  address_line_2 text,
  city text,
  state text check (state is null or char_length(btrim(state)) = 2),
  zip_code text,
  dora_license_number text,
  dora_license_status text,
  source_name text,
  source_url text,
  verified_at timestamptz,
  is_active boolean not null default true,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint property_management_companies_normalized_name_key
    unique (normalized_name)
);

create table if not exists public.property_management_contacts (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null
    references public.property_management_companies(id)
    on update cascade
    on delete restrict,
  full_name text not null check (btrim(full_name) <> ''),
  normalized_name text generated always as (
    lower(regexp_replace(btrim(full_name), '[[:space:]]+', ' ', 'g'))
  ) stored,
  first_name text,
  last_name text,
  title text,
  business_email text
    check (business_email is null or position('@' in business_email) > 1),
  normalized_email text generated always as (
    nullif(lower(btrim(business_email)), '')
  ) stored,
  direct_phone text,
  mobile_phone text,
  address_line_1 text,
  address_line_2 text,
  city text,
  state text check (state is null or char_length(btrim(state)) = 2),
  zip_code text,
  linkedin_url text,
  source_name text,
  source_url text,
  verified_at timestamptz,
  is_current boolean not null default true,
  do_not_contact boolean not null default false,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists property_management_companies_active_name_idx
  on public.property_management_companies (is_active, normalized_name);

create index if not exists property_management_companies_email_domain_idx
  on public.property_management_companies (lower(email_domain))
  where email_domain is not null;

create index if not exists property_management_contacts_company_idx
  on public.property_management_contacts (company_id, is_current, normalized_name);

create index if not exists property_management_contacts_email_idx
  on public.property_management_contacts (normalized_email)
  where normalized_email is not null;

-- Prevent an identical contact from being entered twice for the same company
-- while still allowing two people to share a general office email address.
create unique index if not exists property_management_contacts_identity_key
  on public.property_management_contacts (
    company_id,
    normalized_name,
    coalesce(normalized_email, '')
  );

create or replace function public.set_property_management_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists property_management_companies_set_updated_at
  on public.property_management_companies;
create trigger property_management_companies_set_updated_at
before update on public.property_management_companies
for each row execute function public.set_property_management_updated_at();

drop trigger if exists property_management_contacts_set_updated_at
  on public.property_management_contacts;
create trigger property_management_contacts_set_updated_at
before update on public.property_management_contacts
for each row execute function public.set_property_management_updated_at();

comment on table public.property_management_companies is
  'Property-management organizations. Building and property assignments are modeled separately.';
comment on column public.property_management_companies.normalized_name is
  'Generated comparison value used to prevent duplicate company names.';
comment on table public.property_management_contacts is
  'Current and historical business contacts associated with property-management companies.';
comment on column public.property_management_contacts.verified_at is
  'Most recent time the contact role and business details were independently verified.';
comment on column public.property_management_contacts.do_not_contact is
  'Operational suppression flag that must be honored by outreach workflows.';

-- No browser-facing policies are created in phase 1. With RLS enabled, these
-- tables are available to the Supabase service role until PCS roles and access
-- rules are defined explicitly.
alter table public.property_management_companies enable row level security;
alter table public.property_management_contacts enable row level security;

commit;
