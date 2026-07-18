-- Canonical, non-destructive schema for building footprints.
-- PostGIS must already be enabled in the Supabase project.
CREATE TABLE IF NOT EXISTS building_footprints (
    id               BIGSERIAL PRIMARY KEY,

    external_id      TEXT NOT NULL,

    state            CHAR(2) NOT NULL DEFAULT 'CO',
    county           TEXT NOT NULL,
    municipality     TEXT,

    geometry         geometry(MultiPolygon, 4326) NOT NULL,
    centroid         geometry(Point, 4326),

    footprint_sqft   NUMERIC(12,2),
    perimeter_ft     NUMERIC(12,2),

    source           TEXT NOT NULL,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_building_footprints_source_external_id
        UNIQUE (source, external_id)
);

-- Spatial index for building polygons
CREATE INDEX IF NOT EXISTS idx_building_footprints_geometry
    ON building_footprints
    USING GIST (geometry);

-- Spatial index for centroids
CREATE INDEX IF NOT EXISTS idx_building_footprints_centroid
    ON building_footprints
    USING GIST (centroid);

-- Index for county searches
CREATE INDEX IF NOT EXISTS idx_building_footprints_county
    ON building_footprints (county);
