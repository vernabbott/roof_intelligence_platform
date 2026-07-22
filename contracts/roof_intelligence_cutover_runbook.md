# Roof Intelligence Supabase Cutover Runbook

Status: preparation contract; no application path is connected by this file.

## Safety guarantees

- Every flag defaults to disabled.
- The master flag by itself leaves local reads, local writes, and the local
  worker active.
- A subordinate flag is inert unless the master flag is enabled.
- Shadow writes retain the local SQLite/filesystem result as authoritative and
  must never fail or delay the current report when the staging copy fails.
- The Supabase service-role key is worker/server-only. It must never be stored
  in PCS browser code, a packaged desktop client, source control, or a public
  GitHub variable.
- Existing test reports and files are not migrated.
- No production cutover occurs until the separate staging project passes the
  acceptance gates below.

## Flags

| Flag | Effect when master is enabled |
| --- | --- |
| `ROOF_INTELLIGENCE_SUPABASE_READS_ENABLED` | PCS reads jobs, history, revisions, and assets from Supabase. |
| `ROOF_INTELLIGENCE_SUPABASE_WRITES_ENABLED` | New PCS requests and revision commands are written to Supabase. |
| `ROOF_INTELLIGENCE_SUPABASE_WORKER_ENABLED` | PilotPoint claims and completes Supabase jobs. |
| `ROOF_INTELLIGENCE_SUPABASE_SHADOW_WRITES_ENABLED` | Local writes remain authoritative while equivalent staging records are copied for comparison. |

The master flag is `ROOF_INTELLIGENCE_SUPABASE_ENABLED`. Full cutover is true
only when reads, writes, and worker are enabled and shadow writes are disabled.

## Preparation phases

### 0. Current production baseline

Keep all five flags at `0`. PCS continues to use SQLite/local files and its
current local PilotPoint process. The empty additive Supabase tables have no
runtime effect.

Exit gate: both complete application test suites pass and a current local
report can still be created, viewed, and downloaded.

### 1. Separate staging project

Create the approved Supabase staging project, apply the reporting migrations in
ledger order, and provision separate staging buckets and secrets. Use only
synthetic reports; do not copy existing PDFs, images, health checks, JSON, or
SQLite rows.

Exit gate: migrations rehearse cleanly, all reporting tables begin empty, RLS
is enabled, browser roles cannot claim jobs, and the worker role can.

### 2. Adapter tests with flags off

Implement the PCS repository, PilotPoint worker repository, private asset
upload/download, and immutable revision service against staging. Keep all flags
off in the normal PCS and PilotPoint environments. Exercise adapters only from
tests and explicit staging commands.

Exit gate: a synthetic job produces Revision 1, a private PDF and report image,
checksums, a Ready technical state, and a 90-day retention date.

### 3. Shadow-write comparison

Use `master=1`, `writes=1`, and `shadow_writes=1` in a controlled staging build.
Keep reads and worker cutover disabled. The existing local result remains the
one PCS shows; staging receives a best-effort comparison copy.

Exit gate: repeated job creation is idempotent, field-by-field snapshots match,
failed staging copies do not affect local jobs, and no secrets reach the client.

### 4. Staging end-to-end cutover

In staging only, enable reads, writes, and worker with shadow writes disabled.
Test new reports, complete history, manual revisions, recalculation, fresh
reruns, optional future square-footage overrides, signed asset access, failure
recovery, concurrent worker claims, and retention cleanup.

Exit gate: all acceptance cases pass and rollback to all flags off restores the
local test workflow without database or file repair.

### 5. Production cutover

Before changing flags, stop accepting a new job for only the time needed to
drain or explicitly fail/requeue the small local queue. Record its counts. Then
deploy the already-tested adapters and enable reads, writes, and worker as one
coordinated configuration change. Shadow writes remain disabled.

Exit gate: create one controlled production report, verify its PCS history and
private assets, then restore normal job submission. This is technical smoke
verification; users do not have to approve every report.

## Rollback

If the production smoke test fails, disable the master flag. This returns all
three operations to the local path. Do not delete Supabase rows or assets; keep
them for diagnosis and the normal 90-day policy. Reconcile any jobs submitted
during the cutover window by idempotency key before retrying.

Rollback is complete when PCS can again create, display, and download a local
test report and the local worker has no duplicate queued job.

## Items that must remain unresolved until their prerequisites exist

- PCS browser policies and user identity mapping wait for PCS authentication.
- Staging connection tests wait for the staging project URL and worker secret.
- Production flags remain off until the staging acceptance gates are recorded.
- The long-running PilotPoint worker host remains a deployment decision; GitHub
  is suitable for source and CI but not by itself for an always-on worker.
