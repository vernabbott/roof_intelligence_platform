# Canonical Building Footprint Workflow

`building_footprints` stores raw source records. It may contain Microsoft and
official county records for the same physical structure. Reports do not treat
those rows as separate buildings: `canonical_building_footprints` identifies
the selected raw row and records the reconciliation status.

Statuses:

- `validated`: independent sources differ by no more than 5%.
- `single_source`: only one suitable footprint is available.
- `pending_review`: sources differ by more than 5%.
- `manually_resolved`: a reviewer selected the authoritative source and gave a reason.

The canonical table references raw geometry instead of copying it. Source
links are retained in `building_footprint_source_matches`; manual decisions
are append-only in `canonical_footprint_resolutions`.

## Operations

Install or check the schema:

```bash
./.venv/bin/python scripts/migrate_canonical_footprints.py
./.venv/bin/python scripts/migrate_canonical_footprints.py --apply
```

Pre-reconcile an important property before a report request:

```bash
./.venv/bin/python scripts/reconcile_selected_footprint.py \
  --county denver \
  --address "65 N Yuma St, Denver, CO 80223"
```

List or resolve the review queue:

```bash
./.venv/bin/python scripts/review_canonical_footprints.py
./.venv/bin/python scripts/review_canonical_footprints.py \
  --resolve 123 --source county \
  --reason "County outline follows the current assessor sketch" \
  --reviewer "PCS local user"
```

PCS exposes the same pending queue on the Roof Intelligence workspace.
Resolved decisions are reused by single-address, map, standalone, and bulk
report paths. Report-time comparison remains a safety net for properties that
have not yet been reconciled or whose source data changed.

Automatic canonical selections backed by Microsoft footprints are compared
with the bounded county source again when a linked raw source changes or when
the canonical decision is more than 30 days old. Manual county selections are
not silently replaced by this automatic refresh.

Official county sources are cached only for selected or reconciled properties.
The four available layers contain roughly 1.34 million rows, so a full duplicate
county warehouse is intentionally avoided. The bounded importer remains
available for controlled backfills:

```bash
./.venv/bin/python data/scripts/import_county_footprints.py \
  --county denver --max-records 1000 --apply
```
