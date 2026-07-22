# Roof Intelligence Report Snapshot v1

Status: approved business contract, July 22, 2026.

This contract is based on the user's approved report, revision, calculation,
access, and retention decisions. The current PCS and PilotPoint entry points do
not load this file.

## Report identity and history

- A fresh assessment creates a new logical report with Revision 1.
- A manual edit creates the next immutable revision of that report.
- Every revision stores its own complete snapshot, PDF, and report image.
- PCS will show the newest Ready revision by default and allow access to every
  retained report and revision.
- Ready is a technical state, not a human approval requirement.

## Fresh assessment rule

A rerun refreshes all GIS, assessor, imagery, AI, roof, condition, narrative,
and calculation data. Report-level manual edits never carry into the new
assessment. The only exception is a square-footage correction explicitly saved
as a property-level override for future reports.

## Editable revision fields

- Roof area in square feet
- Roof type
- Roof system/information
- Roof condition score
- Report summary
- Recommendation

Summary and recommendation edits are preserved exactly in that revision. A
future fresh assessment generates both narratives again from refreshed data.
If roof type, roof system, or condition changes and the user does not supply a
recommendation edit, the revision service must refresh the recommendation
before generating the PDF. The summary is never silently rewritten.

## Recalculation rule

The active pricing formulas and rates are not editable. Editing roof area or
condition score reruns the fixed calculations for roof squares, replacement,
overlay, coating, contingencies, warranty ranges, condition label, and risk
level. Each revision records the calculation version and resolved outputs.

## Access and accountability

PCS begins with one user but the data model is multi-user. Any authenticated
user may create a revision. Each revision records the actor, timestamp, parent,
changed fields, and required change reason.

## Retention

A logical report and all its revisions are retained for 90 days after the most
recent revision. Database snapshots and private Storage assets are purged
together only after that retention point.

## Cutover

The current local workflow remains authoritative until the Supabase master,
read, write, and worker flags are deliberately enabled. Subordinate flags have
no effect while the master flag is disabled. Enabling only the master does not
disable any local path. Shadow writes keep local persistence authoritative
while sending comparison copies to staging. Full cutover requires the read,
write, and worker flags together with shadow writes disabled.
