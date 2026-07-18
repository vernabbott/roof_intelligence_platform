# PilotPoint IQ Building Footprint Importer

The importer streams Microsoft building footprints, selects the configured
Colorado counties, and writes them to `building_footprints` in Supabase.
Run all commands below from the repository root.

## Setup

Keep all Census shapefile components together in `data/counties/`, then run:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r data/scripts/requirements.txt
cp data/scripts/.env.example .env
```

Edit `.env` and set the database connection values. Do not commit `.env`.
Supabase direct connections generally require IPv6. If the direct hostname is
unreachable, copy the Session pooler connection string from the Supabase
**Connect** dialog into `DATABASE_URL`.

For an existing table created before duplicate protection was added, run
`docs/ai/supabase/building_footprints_duplicate_protection.sql` once in the
Supabase SQL editor. New tables should be created with
`docs/ai/supabase/building_footprints.sql`.

## Smoke test

This processes only the first 10,000 source features selected by the bounding
box and never connects to the database:

```bash
./.venv/bin/python data/scripts/import_building_footprints.py \
  --buildings data/Colorado.geojson \
  --counties data/counties/tl_2025_us_county.shp \
  --max-features 10000 \
  --dry-run
```

Remove `--max-features 10000` for a complete dry run.

## Import

The normal import appends new footprints and skips existing `(source,
external_id)` values:

```bash
./.venv/bin/python data/scripts/import_building_footprints.py \
  --buildings data/Colorado.geojson \
  --counties data/counties/tl_2025_us_county.shp
```

To replace only the Microsoft source rows, add `--replace-source`. Existing
source rows are deleted first; subsequent batches commit independently. The
importer never truncates unrelated sources.

`--read-chunk-size` controls memory use and commit boundaries (default 10,000
source features), while `--chunk-size` controls individual database INSERTs
(default 5,000 rows). Each source batch uses a fresh database connection and
commits independently, so an interrupted run can safely be rerun; existing
`(source, external_id)` rows are skipped.

## Canonical and county sources

Do not mix multiple sources in report discovery. Install the canonical schema
with `scripts/migrate_canonical_footprints.py --apply`; source-aware reads then
return approved canonical records plus unreconciled Microsoft records.

`import_county_footprints.py` can cache official Denver, Adams, Arapahoe, and
Jefferson outlines as separately tagged raw rows. Prefer
`scripts/reconcile_selected_footprint.py` for request-time or preflight caching
so the database does not duplicate all 1.34 million county records.
