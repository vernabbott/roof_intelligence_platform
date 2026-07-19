-- Non-destructive canonical-footprint layer.
-- building_footprints remains the immutable/raw source table.

ALTER TABLE building_footprints
    ADD COLUMN IF NOT EXISTS parcel_id TEXT,
    ADD COLUMN IF NOT EXISTS source_url TEXT,
    ADD COLUMN IF NOT EXISTS source_updated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_building_footprints_source_county
    ON building_footprints (source, county);
CREATE INDEX IF NOT EXISTS idx_building_footprints_parcel
    ON building_footprints (state, county, parcel_id)
    WHERE parcel_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS canonical_building_footprints (
    id                           BIGSERIAL PRIMARY KEY,
    canonical_key                TEXT NOT NULL UNIQUE,
    state                        CHAR(2) NOT NULL DEFAULT 'CO',
    county                       TEXT NOT NULL,
    parcel_id                    TEXT,
    requested_address             TEXT,
    resolution_status            TEXT NOT NULL CHECK (
        resolution_status IN ('validated', 'single_source', 'pending_review', 'manually_resolved')
    ),
    selected_source_footprint_id BIGINT NOT NULL REFERENCES building_footprints(id),
    selected_source              TEXT NOT NULL,
    source_count                 INTEGER NOT NULL DEFAULT 1,
    difference_pct               NUMERIC(8,3),
    confidence                   NUMERIC(5,4),
    validation_details           JSONB NOT NULL DEFAULT '{}'::jsonb,
    validated_at                 TIMESTAMPTZ,
    resolved_at                  TIMESTAMPTZ,
    resolved_by                  TEXT,
    resolution_reason            TEXT,
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE canonical_building_footprints
    ADD COLUMN IF NOT EXISTS requested_address TEXT;

CREATE INDEX IF NOT EXISTS idx_canonical_building_county_status
    ON canonical_building_footprints (state, county, resolution_status);
CREATE INDEX IF NOT EXISTS idx_canonical_building_parcel
    ON canonical_building_footprints (state, county, parcel_id)
    WHERE parcel_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS building_footprint_source_matches (
    canonical_footprint_id BIGINT NOT NULL REFERENCES canonical_building_footprints(id) ON DELETE CASCADE,
    source_footprint_id    BIGINT NOT NULL REFERENCES building_footprints(id) ON DELETE CASCADE,
    overlap_pct            NUMERIC(8,3),
    area_difference_pct    NUMERIC(8,3),
    match_method           TEXT NOT NULL DEFAULT 'spatial_overlap',
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (canonical_footprint_id, source_footprint_id),
    UNIQUE (source_footprint_id)
);

CREATE TABLE IF NOT EXISTS canonical_footprint_resolutions (
    id                     BIGSERIAL PRIMARY KEY,
    canonical_footprint_id BIGINT NOT NULL REFERENCES canonical_building_footprints(id) ON DELETE CASCADE,
    previous_status        TEXT,
    selected_source        TEXT NOT NULL,
    selected_source_footprint_id BIGINT REFERENCES building_footprints(id),
    reason                 TEXT NOT NULL,
    resolved_by            TEXT NOT NULL,
    validation_details     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE building_footprints IS
    'Raw source footprints. Multiple rows may represent the same physical building.';
COMMENT ON TABLE canonical_building_footprints IS
    'Resolved source of truth used by Roof Intelligence report generation.';
