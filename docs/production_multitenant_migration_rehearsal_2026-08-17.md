# Production multi-tenant migration rehearsal — 2026-08-17

## Scope

This rehearsal validates `20260817163527_prepare_production_multitenant_cutover.sql`
against a disposable local Supabase database shaped from the current production
schema and a read-only export of the production proposal/contact data. No
production database rows were changed.

Large shared reference datasets, including footprint and aerial-image data, were
not copied into the rehearsal database.

## Production-shaped input

| Table | Rows |
| --- | ---: |
| `proposal` | 400 |
| `contact` | 1,008 |
| `organization` | 495 |
| `organization_contact` | 1,008 |
| `proposal_contact` | 397 |
| `property_management_companies` | 162 |
| `property_management_contacts` | 436 |

## Verified results

- The migration completed in one transaction on a clean replay.
- All 400 proposals received exactly one `proposal_tracking` row.
- All 88 records that intentionally require no follow-up were preserved as
  `follow_up_required = false`.
- The current eligible follow-up queue contains one proposal after migration,
  matching the production snapshot used for the rehearsal.
- Contact, organization, proposal-contact, and property-management row counts
  were preserved.
- Normalized tracking values matched the retained legacy proposal lifecycle
  columns with zero mismatches.
- Updating normalized tracking data synchronized the retained legacy columns,
  preserving the rollback path.
- A user assigned to the PCS tenant could read its 400 proposals; a user assigned
  only to a second tenant could read none of them.
- Cross-tenant relationship inserts were rejected.
- Private tenant-membership helper functions were not executable by `anon` or
  `PUBLIC`.
- Supabase security and performance advisors reported no issues.

## Regression checks

- PilotPoint: 193 tests passed.
- PCS integration application: 199 tests passed.
- Restored beta Supabase database: 400 proposals, 400 tracking rows, 88 records
  with follow-up disabled, and 17 applied migrations.
- Local application health after restoration: production landing page `200`,
  beta sign-in `200`, and integration sign-in `200`.

## Cutover constraint

The migration is prepared and rehearsed but has not been applied to the hosted
production Supabase project. Before production cutover, create the initial
production user-to-tenant memberships and take a fresh database backup/export.
