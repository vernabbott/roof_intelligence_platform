#!/usr/bin/env python3
"""Collect assessor apartment and commercial property records."""

from __future__ import annotations

import argparse
import csv
import json
import os
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from county_config import county_profile

ASSESSOR_URL = county_profile("denver").assessor_url

PAGE_SIZE = 2000

ASSESSOR_FIELDS = [
    "PARID",
    "OWNER",
    "CO_OWNER",
    "OWNER_NUM",
    "OWNER_DIR",
    "OWNER_ST",
    "OWNER_TYPE",
    "OWNER_APT",
    "OWNER_CITY",
    "OWNER_STATE",
    "OWNER_ZIP",
    "SITE_NBR",
    "SITE_DIR",
    "SITE_NAME",
    "SITE_MODE",
    "SITE_MORE",
    "TAX_DIST",
    "PROP_CLASS_LAND",
    "PROP_CLASS_IMPS",
    "PROPERTY_CLASS_DESC",
    "BLD_NAME",
    "GROSS_AREA",
    "NET_AREA",
    "NO_FLOORS",
    "TOTL_SQFT",
    "ZONE10",
    "D_CLASS_CN",
    "ORIG_YOC",
    "REMODEL",
    "ASMT_APPR_LAND",
    "ASMT_APPR_IMPR",
    "TOTAL_VALUE",
    "TOT_UNITS",
    "NBHD_CD",
    "NBHD_1_CN",
]

OPTIONAL_EFFECTIVE_YEAR_FIELDS = [
    "EFFECTIVE_YEAR_BUILT",
    "EFF_YEAR_BUILT",
    "EFF_YR_BUILT",
    "EFF_YOC",
    "COM_EFFECTIVE_YEAR_BUILT",
    "COM_EFF_YEAR_BUILT",
]

_COLLECT_FIELDS: list[str] | None = None


def metadata_url(url: str) -> str:
    clean_url = url.split("?", 1)[0].rstrip("/")
    if clean_url.endswith("/query"):
        clean_url = clean_url[: -len("/query")]
    return clean_url


def fetch_json(url: str) -> dict:
    separator = "&" if "?" in url else "?"
    request = Request(
        url if "f=json" in url else url + separator + "f=json",
        headers={"User-Agent": "Python Assessor Collector"},
    )
    try:
        with urlopen(request, timeout=60) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"HTTP error: {exc.code} {exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"URL error: {exc}") from exc


def inspect_service_metadata(url: str = ASSESSOR_URL) -> dict:
    """Return the assessor table metadata."""
    return fetch_json(metadata_url(url))


def available_fields(url: str = ASSESSOR_URL) -> list[dict]:
    metadata = inspect_service_metadata(url)
    return metadata.get("fields", [])


def collect_fields(url: str = ASSESSOR_URL) -> list[str]:
    global _COLLECT_FIELDS
    if _COLLECT_FIELDS is not None:
        return _COLLECT_FIELDS
    field_names = {field.get("name") for field in available_fields(url)}
    _COLLECT_FIELDS = ASSESSOR_FIELDS + [
        field for field in OPTIONAL_EFFECTIVE_YEAR_FIELDS if field in field_names
    ]
    return _COLLECT_FIELDS


def fetch_page(url: str, where: str, offset: int, out_fields: Iterable[str]) -> dict:
    params = {
        "where": where,
        "outFields": ",".join(out_fields),
        "returnGeometry": "false",
        "f": "json",
        "resultOffset": offset,
        "resultRecordCount": PAGE_SIZE,
        "orderByFields": "OBJECTID ASC",
    }
    return fetch_json(url + "?" + urlencode(params))


def collect_assessor_data(url: str | None = ASSESSOR_URL, limit: int | None = None) -> list[dict]:
    """Fetch apartment and commercial assessor records from a configured source."""
    if not url:
        return []
    offset = 0
    results: list[dict] = []
    while True:
        page = fetch_page(url, "1=1", offset, collect_fields(url))
        features = page.get("features", [])
        if not features:
            break
        for feature in features:
            results.append(feature.get("attributes", {}))
            if limit and len(results) >= limit:
                return results[:limit]
        offset += PAGE_SIZE
        if len(features) < PAGE_SIZE:
            break
    return results


def collect_denver_assessor_data(limit: int | None = None) -> list[dict]:
    """Fetch Denver apartment and commercial assessor records."""
    return collect_assessor_data(ASSESSOR_URL, limit)


def write_csv(records: list[dict], output_path: str, fields: list[str] | None = None) -> None:
    fields = fields or collect_fields()
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fields})


def parse_args() -> argparse.Namespace:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_output = os.path.join(script_dir, "denver_assessor_sample.csv")
    parser = argparse.ArgumentParser(description="Collect assessor apartment and commercial records.")
    parser.add_argument("--county", default="denver", help="County profile key")
    parser.add_argument("--output", default=default_output, help="CSV output file path")
    parser.add_argument("--limit", type=int, default=100, help="Maximum records to write")
    parser.add_argument("--list-fields", action="store_true", help="Print available assessor fields and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile = county_profile(args.county)
    if not profile.assessor_url:
        print(f"{profile.display_name} does not have an assessor source configured.")
        return 0

    metadata = inspect_service_metadata(profile.assessor_url)
    spatial_reference = metadata.get("spatialReference") or {}
    print(f"Assessor CRS: {spatial_reference.get('latestWkid') or spatial_reference.get('wkid') or spatial_reference}")

    fields = available_fields(profile.assessor_url)
    print("Available assessor fields:")
    for field in fields:
        print(f"- {field.get('name')} ({field.get('alias')})")

    if args.list_fields:
        return 0

    fields_to_write = collect_fields(profile.assessor_url)
    records = collect_assessor_data(profile.assessor_url, args.limit)
    write_csv(records, args.output, fields_to_write)
    print(f"Saved {len(records)} assessor records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
