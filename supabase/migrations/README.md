# PCS Supabase database baseline

The SQL migrations in this directory are ordered by their timestamp prefixes.

## Local beta database

This beta repository is the migration ledger for the shared PCS/PilotPoint
local Supabase stack. The local stack creates the same database structures used
by both beta applications but loads only `supabase/seed.sql`, which contains a
small synthetic contact, organization, and proposal set. In particular,
`building_footprints` is created empty and the production footprint corpus is
not copied.

```sh
npm install
colima start
npm run supabase:start
npm run supabase:reset
npm run supabase:status
```

The API is available only on the local machine at `http://127.0.0.1:54321`.
Stop the services with `npm run supabase:stop` and `colima stop` when they are
not needed.

The initial files are a version-controlled baseline of database changes that
were already applied manually to the PCS Supabase project. Before using the
Supabase CLI to push later migrations, mark these baseline versions as applied
in the project's migration history rather than executing them as new changes.

## Applied baseline

Baseline recorded and verified on July 19, 2026.

| Migration | PCS status |
|---|---|
| `20260719000100_create_building_footprints.sql` | Applied |
| `20260719000200_add_building_footprint_duplicate_protection.sql` | Applied |
| `20260719000300_create_canonical_building_footprints.sql` | Applied |
| `20260719000400_create_property_management_phase_one.sql` | Applied and verified |

Phase 1 verification against the live PCS database confirmed:

- Both property-management tables exist.
- The company-name and contact-identity unique indexes reject normalized duplicates.
- Both `updated_at` triggers execute successfully.
- Row-level security is enabled on both tables.
- The `service_role` can insert company and contact records.
- The `anon` role cannot view protected rows or insert records.
- Verification transactions left no test records in either table.

## Scope boundary

The Phase 1 baseline stores property-management companies and their contacts
only. It does not associate a company or contact with a property, parcel,
building footprint, roof report, or other building record. Those relationships
are future feature work and require a separate migration and design review.

## Roof Intelligence reporting structure

| Migration | PCS status |
|---|---|
| `20260722000100_create_roof_intelligence_reporting.sql` | Applied and verified July 22, 2026 |
| `20260722000200_prepare_roof_intelligence_cutover.sql` | Applied and verified July 22, 2026 |
| `20260722000300_add_report_edit_requests_and_authenticated_access.sql` | Prepared locally; not applied |
| `20260726000100_add_reviewed_processing_feedback.sql` | Prepared locally; not applied; depends on `20260722000300` |
| `20260805000100_create_contact_organization_model.sql` | Consolidated current model for empty local beta databases |
| `20260805000200_create_proposal_tracking.sql` | Current four-state proposal model for empty local beta databases |
| `20260805145432_add_multi_tenant_foundation.sql` | Permanent beta tenant, membership, role, settings, report-folder, RLS, and Storage isolation foundation |
| `20260805162011_normalize_proposal_tracking.sql` | Splits customer/project identity into `proposal` and lifecycle fields into a tenant-scoped one-to-one `proposal_tracking` row |

This migration creates empty centralized Roof Intelligence job, property,
report, immutable revision, asset, notification, and county-health structures,
plus private PDF and image buckets. It intentionally imports none of the local
test reports or artifacts and does not change PCS or PilotPoint runtime behavior.

The multi-tenant migration replaces the earlier broad authenticated report
policies with membership-based row-level security. It also gives every
tenant-owned business and report record a required `tenant_id`, while keeping
the large footprint and canonical property datasets shared and read-only.
PCS uses a publishable key plus the signed-in user's JWT; only the protected
PilotPoint worker may use the service role.

The proposal normalization migration uses `proposal_tracking.proposal_id` as
its primary key and a tenant-matching foreign key to `proposal`. Customer name,
project address, city, state, ZIP, display name, and proposal-folder identity
exist only on `proposal`; tracking assignments, dates, response, status, and
source-reconciliation fields exist only on `proposal_tracking`.

Live verification confirmed that all eight tables were empty after creation,
both Storage buckets were private, row-level security was enabled on every new
table, and no browser-facing policies existed. The configured Supabase project
does not currently contain a `supabase_migrations.schema_migrations` history
table, so this repository ledger remains the record of manually applied
baseline migrations.

The cutover-preparation migration was rehearsed with a forced rollback before
application. Follow-up verification confirmed that its property-override table
was empty, its retention and override lifecycle passed inside a rolled-back
transaction, and only `service_role` can execute the atomic worker-claim
function. PCS and PilotPoint do not call these structures yet.

The report-edit migration adds an authenticated, idempotent request queue. The
later multi-tenant migration scopes that queue and its security-definer RPC to
the actor's active company membership. Local beta is the current rehearsal
environment; no paid hosted beta project is required.

The reviewed-processing-feedback migration adds an explicit opt-in flag to
report edits and creates a human-reviewed correction queue. Pending and
approved records do not affect report generation. A correction becomes usable
only after an authorized maintainer records the workflow version and durable
guide, manifest, reference, known-building, prompt, or evaluation artifacts
that apply it. Review and application functions are restricted to the service
role.
