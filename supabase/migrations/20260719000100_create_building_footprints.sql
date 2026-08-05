-- Canonical, non-destructive schema for building footprints.
-- Declare the PostGIS dependency so this baseline can initialize an empty
-- local beta database as well as a hosted project where it is already enabled.
CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions;

CREATE TABLE IF NOT EXISTS building_footprints (
    id               BIGSERIAL PRIMARY KEY,

    external_id      TEXT NOT NULL,

    state            CHAR(2) NOT NULL DEFAULT 'CO',
    county           TEXT NOT NULL,
    municipality     TEXT,

    geometry         extensions.geometry(MultiPolygon, 4326) NOT NULL,
    centroid         extensions.geometry(Point, 4326),

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
