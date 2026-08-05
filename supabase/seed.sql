-- Small, synthetic beta dataset. No production contacts, reports, imagery, or
-- building-footprint source data are copied into local development.

insert into public.tenant (id, name, slug) values
  ('00000000-0000-4000-8000-000000000002', 'Example Roofing Beta', 'example-roofing-beta')
on conflict (id) do nothing;

insert into public.report_folder (id, tenant_id, name) values
  (
    '00000000-0000-4000-8000-000000000102',
    '00000000-0000-4000-8000-000000000002',
    'Example Reports'
  )
on conflict (id) do nothing;

insert into public.tenant_settings (tenant_id, default_report_folder_id) values
  (
    '00000000-0000-4000-8000-000000000002',
    '00000000-0000-4000-8000-000000000102'
  )
on conflict (tenant_id) do nothing;

insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
  raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
  confirmation_token, recovery_token, email_change_token_new,
  email_change_token_current, email_change, phone_change_token,
  reauthentication_token, is_sso_user, is_anonymous
) values
  (
    '00000000-0000-0000-0000-000000000000',
    '90000000-0000-4000-8000-000000000001',
    'authenticated', 'authenticated', 'owner@pcs-beta.test',
    crypt('PCS-Beta-Owner-2026!', gen_salt('bf')), now(),
    '{"provider":"email","providers":["email"]}'::jsonb,
    '{"full_name":"PCS Beta Owner"}'::jsonb, now(), now(),
    '', '', '', '', '', '', '', false, false
  ),
  (
    '00000000-0000-0000-0000-000000000000',
    '90000000-0000-4000-8000-000000000002',
    'authenticated', 'authenticated', 'owner@example-beta.test',
    crypt('Example-Beta-Owner-2026!', gen_salt('bf')), now(),
    '{"provider":"email","providers":["email"]}'::jsonb,
    '{"full_name":"Example Beta Owner"}'::jsonb, now(), now(),
    '', '', '', '', '', '', '', false, false
  )
on conflict (id) do nothing;

insert into auth.identities (
  id, provider_id, user_id, identity_data, provider,
  last_sign_in_at, created_at, updated_at
) values
  (
    '91000000-0000-4000-8000-000000000001',
    '90000000-0000-4000-8000-000000000001',
    '90000000-0000-4000-8000-000000000001',
    '{"sub":"90000000-0000-4000-8000-000000000001","email":"owner@pcs-beta.test"}'::jsonb,
    'email', now(), now(), now()
  ),
  (
    '91000000-0000-4000-8000-000000000002',
    '90000000-0000-4000-8000-000000000002',
    '90000000-0000-4000-8000-000000000002',
    '{"sub":"90000000-0000-4000-8000-000000000002","email":"owner@example-beta.test"}'::jsonb,
    'email', now(), now(), now()
  )
on conflict (id) do nothing;

insert into public.tenant_membership (tenant_id, user_id, role) values
  (
    '00000000-0000-4000-8000-000000000001',
    '90000000-0000-4000-8000-000000000001',
    'owner'
  ),
  (
    '00000000-0000-4000-8000-000000000002',
    '90000000-0000-4000-8000-000000000002',
    'owner'
  )
on conflict (tenant_id, user_id) do nothing;

insert into public.organization (
  id, tenant_id, name, organization_type, email_domain, main_email, main_phone,
  main_office_address_line_1, main_office_city, main_office_state,
  main_office_zip_code, source_name
) values (
  '10000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000001',
  'Sample Property Group',
  'Property Management',
  'example.test',
  'office@example.test',
  '303-555-0100',
  '100 Market Street',
  'Denver',
  'CO',
  '80202',
  'local_seed'
) on conflict (id) do nothing;

insert into public.contact (
  id, tenant_id, full_name, first_name, last_name, notes
) values (
  '20000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000001',
  'Casey Sample',
  'Casey',
  'Sample',
  'Synthetic local-development contact.'
) on conflict (id) do nothing;

insert into public.organization_contact (
  id, tenant_id, contact_id, organization_id, title, business_email, business_phone,
  is_current, source_name
) values (
  '30000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000001',
  '20000000-0000-4000-8000-000000000001',
  '10000000-0000-4000-8000-000000000001',
  'Property Manager',
  'casey@example.test',
  '303-555-0101',
  true,
  'local_seed'
) on conflict (id) do nothing;

insert into public.proposal (
  id, tenant_id, customer_name, project_street_address, project_city, project_state,
  project_zip_code, lead_source, submitted_by, estimated_by,
  estimate_completed_date, proposal_sent_date, follow_up_date, status,
  proposal_folder_name, source_name, source_row_number
) values
  (
    '40000000-0000-4000-8000-000000000001',
    '00000000-0000-4000-8000-000000000001',
    'Sample Apartments', '101 Test Avenue', 'Denver', 'CO', '80202',
    'Referral', 'Beta Salesperson', 'Beta Estimator',
    current_date - 10, current_date - 9, current_date - 2, 'sent',
    'Sample Apartments - 101 Test Avenue', 'local_seed', 2
  ),
  (
    '40000000-0000-4000-8000-000000000002',
    '00000000-0000-4000-8000-000000000001',
    'Example Offices', '202 Demo Street', 'Aurora', 'CO', '80012',
    'Website', 'Beta Salesperson', 'Beta Estimator',
    current_date - 30, current_date - 28, current_date - 21, 'under_contract',
    'Example Offices - 202 Demo Street', 'local_seed', 3
  ),
  (
    '40000000-0000-4000-8000-000000000003',
    '00000000-0000-4000-8000-000000000001',
    'Training Warehouse', '303 Mockingbird Lane', 'Lakewood', 'CO', '80226',
    'Cold Call', 'Beta Salesperson', 'Beta Estimator',
    current_date - 45, current_date - 43, null, 'dead',
    'Training Warehouse - 303 Mockingbird Lane', 'local_seed', 4
  )
on conflict (id) do nothing;

insert into public.proposal_contact (
  tenant_id, proposal_id, organization_contact_id, contact_role, is_primary
)
select
  '00000000-0000-4000-8000-000000000001'::uuid,
  proposal_id,
  '30000000-0000-4000-8000-000000000001'::uuid,
  'primary',
  true
from unnest(array[
  '40000000-0000-4000-8000-000000000001'::uuid,
  '40000000-0000-4000-8000-000000000002'::uuid,
  '40000000-0000-4000-8000-000000000003'::uuid
]) as proposal_id
on conflict (proposal_id, organization_contact_id) do nothing;
