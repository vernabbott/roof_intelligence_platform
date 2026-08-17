# Production multi-tenant cutover — 2026-08-17

## Backup

A full hosted-production backup was completed before the schema change and is
stored outside the repositories at:

`~/Library/Application Support/PCS Proposal Management/backups/production-supabase/2026-08-17-pre-multitenant/`

The directory is owner-only and contains:

| File | Size | SHA-256 |
| --- | ---: | --- |
| `roles.sql` | 358 bytes | `4350a72b5ec109888e740c17f3eb4da2fcd95ab73af26499538ed0bf615db543` |
| `schema.sql` | 76 KB | `be9994589ba6d85852d8acd8284179916b64372a0f003087e961bcbd757f64da` |
| `data.sql` | 646 MB | `5af6788b217320bb673101a95642fb822be269df327107ae319774ae3b8ae561` |

The data backup includes Auth, Storage, proposal/contact data, and the large
shared reference datasets.

## Applied migrations

- `20260817163527_prepare_production_multitenant_cutover.sql`
- `20260817172300_restrict_rls_auto_enable.sql`

Both versions are recorded as applied in hosted production migration history.
Older production migration-history entries do not share filenames with the
repository's older migration chain; therefore the cutover migrations were
applied explicitly instead of replaying or blindly pushing historical files.

## Data validation

- One PCS tenant was created.
- All 400 proposals were assigned to that tenant.
- Exactly 400 one-to-one `proposal_tracking` rows were created.
- All 88 records with follow-up intentionally disabled were preserved.
- Normalized tracking values and retained rollback columns had zero lifecycle
  mismatches.
- The rollback synchronization trigger was retained.

## Initial owner and access control

- `vern@procoatingsystems.com` was invited through Supabase Auth.
- The user was assigned the active `owner` role for the PCS tenant.
- Owner-context RLS validation returned 400 proposals and 400 tracking rows.
- An unrelated authenticated-user context returned zero proposals, zero
  tracking rows, and zero memberships.
- The invitation callback allowlist contains only the local production and
  integration callback routes on ports 5050 and 5052.

## Security and application verification

- Direct anonymous and authenticated execution of the hosted project's internal
  `public.rls_auto_enable()` event-trigger helper was revoked.
- Supabase leaked-password protection was enabled.
- Hosted Supabase security and performance advisors: no issues found.
- PCS suite: 203 tests passed.
- PilotPoint suite: 193 tests passed.
- Production landing page, beta sign-in, integration sign-in, and integration
  invitation callback all returned HTTP 200 after the migration.

## Remaining cutover gate

The invited owner must accept the invitation and set a password, after which a
real integration-app sign-in and authenticated proposal-management smoke test
must pass before the integration build replaces the production application.

The database password exposed by the Supabase CLI's `db dump --dry-run` output
should be rotated after the authenticated smoke test and before final release.
