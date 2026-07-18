-- Apply this once to the existing building_footprints table before import.
-- It preserves the oldest row for any existing duplicate source/external_id pair.

BEGIN;

DELETE FROM building_footprints duplicate
USING building_footprints keeper
WHERE duplicate.source = keeper.source
  AND duplicate.external_id = keeper.external_id
  AND duplicate.id > keeper.id;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM building_footprints
        WHERE external_id IS NULL
    ) THEN
        RAISE EXCEPTION
            'building_footprints contains NULL external_id values; resolve them before enabling duplicate protection';
    END IF;
END
$$;

ALTER TABLE building_footprints
    ALTER COLUMN external_id SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_building_footprints_source_external_id
    ON building_footprints (source, external_id);

COMMIT;
