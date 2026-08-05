-- Small, synthetic beta dataset. No production contacts, reports, imagery, or
-- building-footprint source data are copied into local development.

insert into public.organization (
  id, name, organization_type, email_domain, main_email, main_phone,
  main_office_address_line_1, main_office_city, main_office_state,
  main_office_zip_code, source_name
) values (
  '10000000-0000-4000-8000-000000000001',
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
  id, full_name, first_name, last_name, notes
) values (
  '20000000-0000-4000-8000-000000000001',
  'Casey Sample',
  'Casey',
  'Sample',
  'Synthetic local-development contact.'
) on conflict (id) do nothing;

insert into public.organization_contact (
  id, contact_id, organization_id, title, business_email, business_phone,
  is_current, source_name
) values (
  '30000000-0000-4000-8000-000000000001',
  '20000000-0000-4000-8000-000000000001',
  '10000000-0000-4000-8000-000000000001',
  'Property Manager',
  'casey@example.test',
  '303-555-0101',
  true,
  'local_seed'
) on conflict (id) do nothing;

insert into public.proposal (
  id, customer_name, project_street_address, project_city, project_state,
  project_zip_code, lead_source, submitted_by, estimated_by,
  estimate_completed_date, proposal_sent_date, follow_up_date, status,
  proposal_folder_name, source_name, source_row_number
) values
  (
    '40000000-0000-4000-8000-000000000001',
    'Sample Apartments', '101 Test Avenue', 'Denver', 'CO', '80202',
    'Referral', 'Beta Salesperson', 'Beta Estimator',
    current_date - 10, current_date - 9, current_date - 2, 'sent',
    'Sample Apartments - 101 Test Avenue', 'local_seed', 2
  ),
  (
    '40000000-0000-4000-8000-000000000002',
    'Example Offices', '202 Demo Street', 'Aurora', 'CO', '80012',
    'Website', 'Beta Salesperson', 'Beta Estimator',
    current_date - 30, current_date - 28, current_date - 21, 'under_contract',
    'Example Offices - 202 Demo Street', 'local_seed', 3
  ),
  (
    '40000000-0000-4000-8000-000000000003',
    'Training Warehouse', '303 Mockingbird Lane', 'Lakewood', 'CO', '80226',
    'Cold Call', 'Beta Salesperson', 'Beta Estimator',
    current_date - 45, current_date - 43, null, 'dead',
    'Training Warehouse - 303 Mockingbird Lane', 'local_seed', 4
  )
on conflict (id) do nothing;

insert into public.proposal_contact (
  proposal_id, organization_contact_id, contact_role, is_primary
)
select
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
