#!/usr/bin/env python3
"""Import official county GIS outlines as raw, source-tagged footprints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlencode


PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

import collect_denver_buildings_with_parcels as collector
from building_footprint_store import county_source_name, upsert_county_source_batch
from county_config import county_profile


SUPPORTED = ("denver", "adams", "arapahoe", "jefferson")


def fetch_page(url: str, oid_field: str, offset: int, page_size: int) -> list[dict]:
    params = {
        "where": "1=1",
        "outFields": oid_field,
        "returnGeometry": "true",
        "outSR": "4326",
        "resultOffset": offset,
        "resultRecordCount": page_size,
        "orderByFields": f"{oid_field} ASC",
        "f": "json",
    }
    payload = collector.fetch_arcgis_json(url + "?" + urlencode(params))
    records = []
    for feature in payload.get("features") or []:
        attrs = feature.get("attributes") or {}
        geometry_text = collector.geometry_to_wkt(feature.get("geometry"))
        if not geometry_text:
            continue
        records.append(
            {
                "external_id": str(attrs.get(oid_field) or ""),
                "OBJECTID": attrs.get(oid_field),
                "building_geometry": geometry_text,
                "footprint_sqft": collector.geometry_area_sqft_wgs84(geometry_text),
                "source_url": url,
                "source_attributes": attrs,
            }
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--county", required=True, choices=SUPPORTED)
    parser.add_argument("--apply", action="store_true", help="Write source rows to Supabase")
    parser.add_argument("--count-only", action="store_true", help="Report the official source row count and exit")
    parser.add_argument("--max-records", type=int, help="Bounded smoke-test/import limit")
    parser.add_argument("--page-size", type=int, default=1000)
    args = parser.parse_args()
    profile = county_profile(args.county)
    metadata = collector.fetch_json(collector.layer_metadata_url(profile.building_url)) or {}
    oid_field = str(metadata.get("objectIdField") or metadata.get("objectIdFieldName") or "OBJECTID")
    if args.count_only:
        payload = collector.fetch_arcgis_json(
            profile.building_url + "?" + urlencode({"where": "1=1", "returnCountOnly": "true", "f": "json"})
        )
        print(json.dumps({"county": profile.display_name, "source_count": int(payload.get("count") or 0)}))
        return 0
    max_page = int(metadata.get("maxRecordCount") or args.page_size)
    page_size = max(1, min(args.page_size, max_page))
    total = 0
    offset = 0
    while True:
        records = fetch_page(profile.building_url, oid_field, offset, page_size)
        if args.max_records is not None:
            records = records[: max(0, args.max_records - total)]
        if not records:
            break
        if args.apply:
            upsert_county_source_batch(profile.display_name, records)
        total += len(records)
        print(json.dumps({"county": profile.display_name, "source": county_source_name(profile.display_name), "processed": total, "applied": args.apply}))
        if len(records) < page_size or (args.max_records is not None and total >= args.max_records):
            break
        offset += len(records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
