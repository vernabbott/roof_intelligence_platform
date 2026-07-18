#!/usr/bin/env python3
"""Check or install the canonical-footprint schema in Supabase/PostGIS."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from sqlalchemy import text

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from building_footprint_store import CANONICAL_TABLE, RAW_TABLE, engine


MIGRATION = PROJECT_DIR / "docs/ai/supabase/canonical_building_footprints.sql"


def schema_status() -> dict:
    with engine().connect() as connection:
        tables = {
            name: bool(connection.execute(text("SELECT to_regclass(:name) IS NOT NULL"), {"name": name}).scalar())
            for name in (
                RAW_TABLE,
                CANONICAL_TABLE,
                "building_footprint_source_matches",
                "canonical_footprint_resolutions",
            )
        }
        columns = {
            row[0]
            for row in connection.execute(
                text(
                    """SELECT column_name FROM information_schema.columns
                       WHERE table_schema = current_schema() AND table_name = :table"""
                ),
                {"table": RAW_TABLE},
            )
        }
    return {
        "tables": tables,
        "raw_metadata_columns": all(
            name in columns
            for name in ("parcel_id", "source_url", "source_updated_at", "imported_at", "source_metadata")
        ),
    }


def apply_migration() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    raw_connection = engine().raw_connection()
    try:
        with raw_connection.cursor() as cursor:
            cursor.execute(sql)
        raw_connection.commit()
    except Exception:
        raw_connection.rollback()
        raise
    finally:
        raw_connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Install or update the non-destructive schema")
    args = parser.parse_args()
    before = schema_status()
    print(f"Before: {before}")
    if args.apply:
        apply_migration()
        print(f"After: {schema_status()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
