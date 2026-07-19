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
