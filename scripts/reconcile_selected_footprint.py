#!/usr/bin/env python3
"""Pre-reconcile one address into the canonical source of truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PCS_DIR = PROJECT_DIR.parent / "PCS Proposal Management"
sys.path.insert(0, str(PROJECT_DIR))

import collect_denver_buildings_with_parcels as collector
from assessor_detail import fetch_assessor_details, validate_assessor_footprint
from building_footprint_store import (
    MICROSOFT_SOURCE,
    collect_source_buildings_in_envelope,
    mark_canonical_pending_review,
    save_canonical_footprint,
)
from county_config import county_profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--county", required=True)
    parser.add_argument("--address", required=True)
    parser.add_argument("--pcs-dir", type=Path, default=DEFAULT_PCS_DIR)
    args = parser.parse_args()
    sys.path.insert(0, str(args.pcs_dir.expanduser().resolve()))
    from roof_intelligence_single_address import (
        collect_live_parcels_for_address,
        configure_collector_for_county,
        find_parcel_for_address,
        select_building_for_address,
    )

    profile = county_profile(args.county)
    configure_collector_for_county(collector, profile)
    parcels = collect_live_parcels_for_address(args.address, collector)
    parcel, score, matched_address = find_parcel_for_address(args.address, parcels, collector)
    parcel_id = collector.parcel_join_key(parcel)
    envelope = collector.get_parcel_bounds_in_building_crs([parcel])
    primary = collect_source_buildings_in_envelope(
        profile.display_name, envelope, MICROSOFT_SOURCE
    )
    primary_rows = collector.combine_data(primary, [parcel]) if primary else []
    primary_matches = [row for row in primary_rows if collector.parcel_join_key(row) == parcel_id]
    secondary = collector.collect_secondary_buildings(None, envelope)
    secondary_rows = collector.combine_data(secondary, [parcel]) if secondary else []
    secondary_matches = [row for row in secondary_rows if collector.parcel_join_key(row) == parcel_id]
    primary_record = (
        select_building_for_address(primary_matches, args.address, collector)
        if primary_matches else None
    )
    secondary_record = (
        select_building_for_address(secondary_matches, args.address, collector)
        if secondary_matches else None
    )
    if primary_record:
        validation = collector.validate_building_footprint_sources(primary_record, secondary)
    elif secondary_record:
        validation = {
            "status": "county_only",
            "secondary_sqft": secondary_record.get("building_footprint_sqft"),
        }
    else:
        raise RuntimeError("No source footprint matched the selected parcel")
    canonical = save_canonical_footprint(
        profile.display_name, parcel_id, primary_record, secondary_record, validation,
        address=matched_address,
    )
    assessor = fetch_assessor_details(profile.key, [parcel_id])
    assessor_validation = validate_assessor_footprint(
        canonical.get("footprint_sqft"), assessor.records
    )
    if assessor_validation.get("status") == "discrepancy":
        mark_canonical_pending_review(canonical["canonical_id"], {
            **assessor_validation, "comparison": "county_assessor"
        })
        canonical["canonical_status"] = "pending_review"
    print(json.dumps({
        "county": profile.display_name,
        "address": matched_address,
        "address_score": score,
        "parcel": parcel_id,
        "canonical": canonical,
        "source_validation": validation,
        "assessor_validation": assessor_validation,
    }, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": " ".join(str(exc).split())[:500]}))
        raise
