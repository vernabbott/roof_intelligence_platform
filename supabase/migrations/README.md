# PCS Supabase database baseline

The SQL migrations in this directory are ordered by their timestamp prefixes.

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

This migration creates empty centralized Roof Intelligence job, property,
report, immutable revision, asset, notification, and county-health structures,
plus private PDF and image buckets. It intentionally imports none of the local
test reports or artifacts and does not change PCS or PilotPoint runtime behavior.

Row-level security is enabled without browser-facing policies. Application
access policies will be added only when the PCS authentication and integration
work begins.

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
