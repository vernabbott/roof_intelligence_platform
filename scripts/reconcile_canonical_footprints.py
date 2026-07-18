#!/usr/bin/env python3
"""Build canonical decisions from imported Microsoft and county raw footprints."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from sqlalchemy import text


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from building_footprint_store import MICROSOFT_SOURCE, county_source_name, engine
from county_config import county_profile


SUPPORTED = ("denver", "adams", "arapahoe", "jefferson")


def counts(connection, county: str) -> dict:
    row = connection.execute(
        text(
            """SELECT
                count(*) FILTER (WHERE resolution_status = 'validated') AS validated,
                count(*) FILTER (WHERE resolution_status = 'single_source') AS single_source,
                count(*) FILTER (WHERE resolution_status = 'pending_review') AS pending_review,
                count(*) FILTER (WHERE resolution_status = 'manually_resolved') AS manually_resolved
               FROM canonical_building_footprints WHERE state = 'CO' AND county = :county"""
        ), {"county": county}
    ).mappings().one()
    return {key: int(value or 0) for key, value in row.items()}


def reconcile(county: str) -> dict:
    county_source = county_source_name(county)
    with engine().begin() as connection:
        connection.execute(text("SET LOCAL statement_timeout = '15min'"))
        connection.execute(
            text(
                """
                WITH ranked AS (
                    SELECT m.id AS microsoft_id, c.id AS county_id,
                           100.0 * ST_Area(ST_Intersection(m.geometry::geography, c.geometry::geography))
                             / NULLIF(ST_Area(ST_Union(m.geometry, c.geometry)::geography), 0) AS overlap_pct,
                           100.0 * abs(m.footprint_sqft - c.footprint_sqft)
                             / NULLIF(m.footprint_sqft, 0) AS difference_pct,
                           row_number() OVER (
                               PARTITION BY m.id ORDER BY
                               ST_Area(ST_Intersection(m.geometry::geography, c.geometry::geography)) DESC
                           ) AS rank
                    FROM building_footprints m
                    JOIN building_footprints c
                      ON c.state = m.state AND c.county = m.county
                     AND c.source = :county_source
                     AND c.geometry && m.geometry AND ST_Intersects(c.geometry, m.geometry)
                    WHERE m.state = 'CO' AND m.county = :county AND m.source = :microsoft_source
                ), best AS (
                    SELECT * FROM ranked WHERE rank = 1 AND overlap_pct >= 20
                ), source_rows AS (
                    SELECT m.id AS microsoft_id, b.county_id, b.overlap_pct, b.difference_pct
                    FROM building_footprints m LEFT JOIN best b ON b.microsoft_id = m.id
                    WHERE m.state = 'CO' AND m.county = :county AND m.source = :microsoft_source
                )
                INSERT INTO canonical_building_footprints (
                    canonical_key, state, county, resolution_status,
                    selected_source_footprint_id, selected_source, source_count,
                    difference_pct, confidence, validation_details, validated_at
                )
                SELECT 'CO:' || :county || ':source:' || microsoft_id, 'CO', :county,
                       CASE WHEN county_id IS NULL THEN 'single_source'
                            WHEN difference_pct <= 5 THEN 'validated'
                            ELSE 'pending_review' END,
                       microsoft_id, :microsoft_source,
                       CASE WHEN county_id IS NULL THEN 1 ELSE 2 END,
                       difference_pct,
                       CASE WHEN county_id IS NULL THEN 0.6
                            WHEN difference_pct <= 5 THEN 1.0 ELSE 0.5 END,
                       jsonb_build_object(
                           'status', CASE WHEN county_id IS NULL THEN 'primary_only'
                                          WHEN difference_pct <= 5 THEN 'validated' ELSE 'discrepancy' END,
                           'difference_pct', round(difference_pct::numeric, 2),
                           'overlap_pct', round(overlap_pct::numeric, 2),
                           'tolerance_pct', 5.0
                       ),
                       CASE WHEN county_id IS NULL OR difference_pct <= 5 THEN NOW() END
                FROM source_rows
                ON CONFLICT (canonical_key) DO UPDATE SET
                    resolution_status = CASE
                        WHEN canonical_building_footprints.resolution_status = 'manually_resolved'
                        THEN canonical_building_footprints.resolution_status
                        ELSE EXCLUDED.resolution_status END,
                    source_count = EXCLUDED.source_count,
                    difference_pct = EXCLUDED.difference_pct,
                    confidence = CASE
                        WHEN canonical_building_footprints.resolution_status = 'manually_resolved'
                        THEN canonical_building_footprints.confidence ELSE EXCLUDED.confidence END,
                    validation_details = EXCLUDED.validation_details,
                    validated_at = CASE
                        WHEN canonical_building_footprints.resolution_status = 'manually_resolved'
                        THEN canonical_building_footprints.validated_at ELSE EXCLUDED.validated_at END,
                    updated_at = NOW()
                """
            ), {"county": county, "county_source": county_source, "microsoft_source": MICROSOFT_SOURCE}
        )
        connection.execute(
            text(
                """
                WITH ranked AS (
                    SELECT m.id AS microsoft_id, c.id AS county_id,
                           100.0 * ST_Area(ST_Intersection(m.geometry::geography, c.geometry::geography))
                             / NULLIF(ST_Area(ST_Union(m.geometry, c.geometry)::geography), 0) AS overlap_pct,
                           100.0 * abs(m.footprint_sqft - c.footprint_sqft)
                             / NULLIF(m.footprint_sqft, 0) AS difference_pct,
                           row_number() OVER (PARTITION BY m.id ORDER BY
                             ST_Area(ST_Intersection(m.geometry::geography, c.geometry::geography)) DESC) AS rank
                    FROM building_footprints m JOIN building_footprints c
                      ON c.state=m.state AND c.county=m.county AND c.source=:county_source
                     AND c.geometry && m.geometry AND ST_Intersects(c.geometry,m.geometry)
                    WHERE m.state='CO' AND m.county=:county AND m.source=:microsoft_source
                ), best AS (SELECT * FROM ranked WHERE rank=1 AND overlap_pct >= 20),
                links AS (
                    SELECT cb.id canonical_id, cb.selected_source_footprint_id microsoft_id,
                           b.county_id, b.overlap_pct, b.difference_pct
                    FROM canonical_building_footprints cb
                    LEFT JOIN best b ON b.microsoft_id=cb.selected_source_footprint_id
                    WHERE cb.state='CO' AND cb.county=:county
                )
                INSERT INTO building_footprint_source_matches
                    (canonical_footprint_id, source_footprint_id, overlap_pct, area_difference_pct)
                SELECT canonical_id, source_id, overlap_pct, difference_pct
                FROM links CROSS JOIN LATERAL unnest(
                    ARRAY[microsoft_id, county_id]::bigint[]
                ) source_id WHERE source_id IS NOT NULL
                ON CONFLICT (source_footprint_id) DO UPDATE SET
                    canonical_footprint_id=EXCLUDED.canonical_footprint_id,
                    overlap_pct=EXCLUDED.overlap_pct,
                    area_difference_pct=EXCLUDED.area_difference_pct
                """
            ), {"county": county, "county_source": county_source, "microsoft_source": MICROSOFT_SOURCE}
        )
        return counts(connection, county)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--county", required=True, choices=SUPPORTED)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    county = county_profile(args.county).display_name.replace(" County", "")
    with engine().connect() as connection:
        source_counts = dict(
            connection.execute(
                text("SELECT source, count(*) FROM building_footprints WHERE state='CO' AND county=:county GROUP BY source"),
                {"county": county},
            ).all()
        )
        print({"county": county, "raw_sources": source_counts, "canonical": counts(connection, county)})
    if args.apply:
        print({"county": county, "canonical_after": reconcile(county)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
