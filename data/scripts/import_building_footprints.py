#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote_plus

import geopandas as gpd
import pyogrio
import shapely
from dotenv import load_dotenv
from psycopg2 import Binary
from psycopg2.extras import execute_values
from shapely.geometry import MultiPolygon, Polygon
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool

TARGET_COUNTIES = [
    "Adams", "Arapahoe", "Boulder", "Broomfield", "Clear Creek",
    "Denver", "Douglas", "Jefferson", "Larimer", "Weld",
]
STATE_FIPS = "08"
STATE_ABBR = "CO"
SOURCE_NAME = "Microsoft US Building Footprints"
SOURCE_PREFIX = "msft-co"
MEASUREMENT_CRS = "EPSG:26913"
OUTPUT_CRS = "EPSG:4326"
DEST_TABLE = "building_footprints"
DEFAULT_CHUNK_SIZE = 5000
DEFAULT_READ_CHUNK_SIZE = 10_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import selected Colorado building footprints into Supabase/PostGIS.")
    parser.add_argument("--buildings", required=True, type=Path, help="Path to Colorado.geojson")
    parser.add_argument("--counties", required=True, type=Path, help="Path to tl_2025_us_county.shp")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="Rows per database insert (default: 5000)")
    parser.add_argument(
        "--read-chunk-size",
        type=int,
        default=DEFAULT_READ_CHUNK_SIZE,
        help="Source features processed and committed at once (default: 10000)",
    )
    parser.add_argument(
        "--replace-source",
        action="store_true",
        help=f"Delete existing rows whose source is {SOURCE_NAME!r} before importing",
    )
    parser.add_argument("--dry-run", action="store_true", help="Process without connecting or writing to Supabase")
    parser.add_argument(
        "--max-features",
        type=int,
        help="Limit source features for a dry-run smoke test; not allowed for a database import",
    )
    args = parser.parse_args()
    if args.chunk_size <= 0:
        parser.error("--chunk-size must be greater than zero")
    if args.read_chunk_size <= 0:
        parser.error("--read-chunk-size must be greater than zero")
    if args.max_features is not None and args.max_features <= 0:
        parser.error("--max-features must be greater than zero")
    if args.max_features is not None and not args.dry_run:
        parser.error("--max-features may only be used with --dry-run")
    return args


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")


def require_file(path: Path, label: str) -> None:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")


def build_database_url() -> str:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    host = os.getenv("SUPABASE_DB_HOST")
    port = os.getenv("SUPABASE_DB_PORT", "5432")
    name = os.getenv("SUPABASE_DB_NAME", "postgres")
    user = os.getenv("SUPABASE_DB_USER", "postgres")
    password = os.getenv("SUPABASE_DB_PASSWORD")
    missing = [k for k, v in {
        "SUPABASE_DB_HOST": host,
        "SUPABASE_DB_PASSWORD": password,
    }.items() if not v]
    if missing:
        raise RuntimeError("Missing database configuration: " + ", ".join(missing))

    return f"postgresql+psycopg2://{user}:{quote_plus(password)}@{host}:{port}/{name}?sslmode=require"


def create_db_engine(database_url: str) -> Engine:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(
        database_url,
        poolclass=NullPool,
        connect_args={
            "sslmode": "require",
            "connect_timeout": 15,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
            "tcp_user_timeout": 60_000,
            "options": "-c statement_timeout=300000",
            "application_name": "pilotpoint_building_importer",
        },
    )


def verify_database(engine: Engine) -> None:
    qualified_table = DEST_TABLE
    with engine.connect() as connection:
        postgis_version = connection.execute(text("SELECT PostGIS_Version();")).scalar_one()
        table_exists = connection.execute(
            text("SELECT to_regclass(:qualified_table) IS NOT NULL;"),
            {"qualified_table": qualified_table},
        ).scalar_one()
        if not table_exists:
            raise RuntimeError(f"Destination table {qualified_table} does not exist.")

        has_unique_source_id = connection.execute(text("""
            SELECT EXISTS (
                SELECT 1
                FROM pg_index i
                WHERE i.indrelid = to_regclass(:qualified_table)
                  AND i.indisunique
                  AND (
                      SELECT array_agg(a.attname::text ORDER BY key_position.ordinality)
                      FROM unnest(i.indkey) WITH ORDINALITY AS key_position(attnum, ordinality)
                      JOIN pg_attribute a
                        ON a.attrelid = i.indrelid
                       AND a.attnum = key_position.attnum
                  ) = ARRAY['source', 'external_id']
            );
        """), {"qualified_table": qualified_table}).scalar_one()
    if not has_unique_source_id:
        raise RuntimeError(
            f"{qualified_table} needs a unique index on (source, external_id). "
            "Run docs/ai/supabase/building_footprints_duplicate_protection.sql first."
        )
    logging.info("Connected to PostGIS %s", postgis_version)


def load_target_counties(county_path: Path) -> gpd.GeoDataFrame:
    logging.info("Reading county boundaries: %s", county_path)
    counties = gpd.read_file(county_path, columns=["STATEFP", "NAME", "geometry"], engine="pyogrio", use_arrow=True)
    if counties.crs is None:
        raise RuntimeError("County shapefile has no CRS")
    counties = counties[
        (counties["STATEFP"].astype(str).str.zfill(2) == STATE_FIPS)
        & counties["NAME"].isin(TARGET_COUNTIES)
    ].copy()
    missing = sorted(set(TARGET_COUNTIES) - set(counties["NAME"]))
    if missing:
        raise RuntimeError("Target counties not found: " + ", ".join(missing))
    counties = counties.to_crs(OUTPUT_CRS).rename(columns={"NAME": "county"})[["county", "geometry"]]
    logging.info("Loaded %d target counties", len(counties))
    return counties


def iter_candidate_buildings(
    building_path: Path,
    counties: gpd.GeoDataFrame,
    read_chunk_size: int,
    max_features: int | None = None,
) -> Iterator[gpd.GeoDataFrame]:
    bbox = tuple(counties.total_bounds)
    logging.info("Streaming footprints within bounding box %s", bbox)
    with pyogrio.open_arrow(
        building_path,
        columns=[],
        bbox=bbox,
        batch_size=read_chunk_size,
        use_pyarrow=True,
    ) as (metadata, reader):
        geometry_column = metadata["geometry_name"] or "wkb_geometry"
        source_crs = metadata["crs"] or OUTPUT_CRS
        if metadata["crs"] is None:
            logging.warning("Building source has no CRS; assuming %s", OUTPUT_CRS)
        remaining = max_features
        for batch in reader:
            if remaining is not None:
                if remaining <= 0:
                    break
                if len(batch) > remaining:
                    batch = batch.slice(0, remaining)
                remaining -= len(batch)
            geometries = shapely.from_wkb(batch[geometry_column])
            buildings = gpd.GeoDataFrame(geometry=geometries, crs=source_crs)
            if buildings.crs != OUTPUT_CRS:
                buildings = buildings.to_crs(OUTPUT_CRS)
            buildings = buildings[buildings.geometry.notna() & ~buildings.geometry.is_empty].copy()
            logging.info("Read candidate batch with %d usable footprints", len(buildings))
            yield buildings


def make_valid_multipolygon(geometry):
    if geometry is None or geometry.is_empty:
        return None
    geometry = shapely.make_valid(geometry) if not geometry.is_valid else geometry
    if geometry.is_empty:
        return None
    if isinstance(geometry, Polygon):
        return MultiPolygon([geometry])
    if isinstance(geometry, MultiPolygon):
        return geometry
    parts = [part for part in getattr(geometry, "geoms", []) if isinstance(part, Polygon)]
    return MultiPolygon(parts) if parts else None


def stable_external_id(geometry) -> str:
    normalized = shapely.normalize(geometry)
    geometry_wkb = shapely.to_wkb(normalized, byte_order=1, include_srid=False)
    return f"{SOURCE_PREFIX}-{hashlib.sha256(geometry_wkb).hexdigest()}"


def prepare_buildings(buildings: gpd.GeoDataFrame, counties: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    logging.info("Validating and normalizing geometries")
    buildings = buildings[["geometry"]].copy()
    buildings["geometry"] = buildings.geometry.apply(make_valid_multipolygon)
    buildings = buildings[buildings.geometry.notna() & ~buildings.geometry.is_empty].copy()
    if buildings.empty:
        return empty_output_frame()

    projected = buildings.to_crs(MEASUREMENT_CRS)
    projected["footprint_sqft"] = projected.geometry.area * 10.7639104167
    projected["perimeter_ft"] = projected.geometry.length * 3.280839895

    assignment_points = gpd.GeoDataFrame(
        {"source_row": projected.index},
        geometry=projected.geometry.representative_point(),
        crs=MEASUREMENT_CRS,
    ).to_crs(OUTPUT_CRS)

    county_lookup = gpd.sjoin(assignment_points, counties, how="inner", predicate="within")[["source_row", "county"]]
    if county_lookup.empty:
        return empty_output_frame()
    county_lookup = county_lookup.drop_duplicates("source_row").set_index("source_row")

    projected = projected.loc[projected.index.intersection(county_lookup.index)].copy()
    projected["county"] = county_lookup.loc[projected.index, "county"]

    output = projected.to_crs(OUTPUT_CRS)
    output["centroid"] = gpd.GeoSeries(projected.geometry.centroid, index=projected.index, crs=MEASUREMENT_CRS).to_crs(OUTPUT_CRS)
    output["external_id"] = output.geometry.apply(stable_external_id)
    output["state"] = STATE_ABBR
    output["municipality"] = None
    output["source"] = SOURCE_NAME
    output["footprint_sqft"] = output["footprint_sqft"].round(2)
    output["perimeter_ft"] = output["perimeter_ft"].round(2)

    output = output[[
        "external_id", "state", "county", "municipality", "geometry", "centroid",
        "footprint_sqft", "perimeter_ft", "source",
    ]]
    return gpd.GeoDataFrame(output, geometry="geometry", crs=OUTPUT_CRS)


def empty_output_frame() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        columns=[
            "external_id", "state", "county", "municipality", "geometry", "centroid",
            "footprint_sqft", "perimeter_ft", "source",
        ],
        geometry="geometry",
        crs=OUTPUT_CRS,
    )


def replace_source_rows(connection: Connection) -> int:
    logging.warning("Replacing existing %s rows atomically", SOURCE_NAME)
    result = connection.execute(
        text(f'DELETE FROM "{DEST_TABLE}" WHERE source = :source'),
        {"source": SOURCE_NAME},
    )
    return result.rowcount


def write_to_postgis(buildings: gpd.GeoDataFrame, connection: Connection, chunk_size: int) -> int:
    insert_sql = f'''\
        INSERT INTO "{DEST_TABLE}"
            (external_id, state, county, municipality, geometry, centroid,
             footprint_sqft, perimeter_ft, source)
        VALUES %s
        ON CONFLICT (source, external_id) DO NOTHING
    '''
    template = (
        "(%s, %s, %s, %s, "
        "ST_SetSRID(ST_GeomFromWKB(%s), 4326), "
        "ST_SetSRID(ST_GeomFromWKB(%s), 4326), %s, %s, %s)"
    )
    rows = [
        (
            row.external_id,
            row.state,
            row.county,
            row.municipality,
            Binary(row.geometry.wkb),
            Binary(row.centroid.wkb),
            row.footprint_sqft,
            row.perimeter_ft,
            row.source,
        )
        for row in buildings.itertuples(index=False)
    ]

    inserted = 0
    raw_connection = connection.connection
    with raw_connection.cursor() as cursor:
        for start in range(0, len(rows), chunk_size):
            execute_values(cursor, insert_sql, rows[start:start + chunk_size], template=template, page_size=chunk_size)
            inserted += cursor.rowcount
    return inserted


def process_buildings(
    building_path: Path,
    counties: gpd.GeoDataFrame,
    read_chunk_size: int,
    chunk_size: int,
    engine: Engine | None = None,
    max_features: int | None = None,
) -> tuple[int, int, Counter[str]]:
    prepared_total = 0
    inserted_total = 0
    county_counts: Counter[str] = Counter()
    for candidates in iter_candidate_buildings(building_path, counties, read_chunk_size, max_features):
        prepared = prepare_buildings(candidates, counties)
        if prepared.empty:
            continue
        prepared_total += len(prepared)
        county_counts.update(prepared["county"])
        batch_inserted = 0
        if engine is not None:
            with engine.begin() as connection:
                batch_inserted = write_to_postgis(prepared, connection, chunk_size)
            inserted_total += batch_inserted
        logging.info(
            "Prepared %d selected footprints so far; committed batch rows=%d skipped=%d",
            prepared_total,
            batch_inserted,
            len(prepared) - batch_inserted if engine is not None else 0,
        )

    if prepared_total == 0:
        raise RuntimeError("No footprints matched the selected counties")
    return prepared_total, inserted_total, county_counts


def verify_import(engine: Engine) -> None:
    with engine.connect() as connection:
        result = connection.execute(text(f'''
            SELECT COUNT(*) AS row_count,
                   COUNT(DISTINCT county) AS county_count,
                   MIN(footprint_sqft) AS min_sqft,
                   MAX(footprint_sqft) AS max_sqft
            FROM "{DEST_TABLE}"
            WHERE source = :source;
        '''), {"source": SOURCE_NAME}).mappings().one()
    logging.info("Source totals: rows=%s counties=%s min_sqft=%s max_sqft=%s",
                 result["row_count"], result["county_count"], result["min_sqft"], result["max_sqft"])


def log_county_counts(county_counts: Counter[str]) -> None:
    logging.info("County counts:\n%s", "\n".join(f"{county}: {county_counts[county]}" for county in sorted(county_counts)))


def main() -> int:
    configure_logging()
    args = parse_args()
    try:
        require_file(args.buildings, "Building GeoJSON")
        require_file(args.counties, "County shapefile")
        counties = load_target_counties(args.counties)

        if args.dry_run:
            prepared, _, county_counts = process_buildings(
                args.buildings,
                counties,
                args.read_chunk_size,
                args.chunk_size,
                max_features=args.max_features,
            )
            log_county_counts(county_counts)
            logging.info("Dry run complete; prepared %d rows and made no database changes", prepared)
            return 0

        engine = create_db_engine(build_database_url())
        try:
            verify_database(engine)
            if args.replace_source:
                with engine.begin() as connection:
                    deleted = replace_source_rows(connection)
            else:
                deleted = 0
            prepared, inserted, county_counts = process_buildings(
                args.buildings,
                counties,
                args.read_chunk_size,
                args.chunk_size,
                engine=engine,
            )
            logging.info(
                "Import prepared %d rows, inserted %d, skipped %d duplicates, and replaced %d old rows",
                prepared,
                inserted,
                prepared - inserted,
                deleted,
            )
            log_county_counts(county_counts)
            verify_import(engine)
        finally:
            engine.dispose()
        return 0
    except Exception:
        logging.exception("Import failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
