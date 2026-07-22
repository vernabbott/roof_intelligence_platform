#!/usr/bin/env python3
"""Bounded live health checks for parcel, footprint, assessor, and imagery discovery."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import sys
from time import perf_counter
import time
from urllib.request import Request, urlopen

from PIL import Image, ImageStat


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_PCS_DIR = PROJECT_DIR.parent / "PCS Proposal Management"
SAMPLE_ADDRESSES = {
    "denver": ("65 N Yuma St, Denver, CO 80223", "500 S Santa Fe Dr, Denver, CO 80223"),
    "adams": ("6345 Colorado Blvd, Commerce City, CO 80022", "5101 Quebec St, Commerce City, CO 80022"),
    "arapahoe": ("9800 E IKEA Way, Centennial, CO 80112", "10900 E Briarwood Ave, Centennial, CO 80112"),
    "jefferson": ("12364 W Alameda Pkwy, Lakewood, CO 80228", "12043 W Alameda Pkwy, Lakewood, CO 80228"),
    "boulder": ("1325 Pearl St, Boulder, CO 80302", "1777 Broadway, Boulder, CO 80302"),
    "broomfield": ("1 DesCombes Dr, Broomfield, CO 80020", "3 Community Park Rd, Broomfield, CO 80020"),
    "clear_creek": ("405 Argentine St, Georgetown, CO 80444", "512 6th St, Georgetown, CO 80444"),
    "douglas": ("2508 Pine Bluff Ln, Highlands Ranch, CO 80126", "100 Third St, Castle Rock, CO 80104"),
    "larimer": ("107 Linden St, Fort Collins, CO 80524", "200 W Oak St, Fort Collins, CO 80521"),
    "weld": ("1150 O St, Greeley, CO 80631", "1000 10th St, Greeley, CO 80631"),
}


def aggregate_sample_status(samples: list[dict]) -> str:
    """Grade a county without treating one property-specific miss as an outage."""
    if not samples:
        return "failed"
    passed = sum(sample.get("status") == "healthy" for sample in samples)
    if passed == len(samples):
        return "healthy"
    if passed:
        return "degraded"
    return "failed"


def aggregate_county_status(results: list[dict]) -> str:
    statuses = {result.get("status") for result in results}
    if "failed" in statuses:
        return "failed"
    if "degraded" in statuses:
        return "degraded"
    return "healthy"


def cleanup_orphan_imagery(max_age_days: int = 7) -> int:
    cutoff = time.time() - max(1, int(max_age_days)) * 86400
    root = PROJECT_DIR / "aerial_images_single_address"
    removed = 0
    if not root.is_dir():
        return removed
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def check_county(county: str, address: str, collector, single, profiles, fetch_assessor_details) -> dict:
    profile = profiles[county]
    timings = {}
    started = perf_counter()
    single.configure_collector_for_county(collector, profile)
    parcels = single.collect_live_parcels_for_address(address, collector)
    timings["parcel_seconds"] = round(perf_counter() - started, 3)
    parcel, score, _ = single.find_parcel_for_address(address, parcels, collector)
    parcel_id = collector.parcel_join_key(parcel)
    envelope = collector.get_parcel_bounds_in_building_crs([parcel])
    started = perf_counter()
    primary = collector.collect_buildings(None, envelope)
    timings["supabase_seconds"] = round(perf_counter() - started, 3)
    primary_rows = collector.combine_data(primary, [parcel])
    primary_matches = [row for row in primary_rows if collector.parcel_join_key(row) == parcel_id]
    if not primary_matches:
        raise RuntimeError("no Supabase footprint matched the parcel")
    selected = single.select_building_for_address(primary_matches, address, collector)

    started = perf_counter()
    secondary = collector.collect_secondary_buildings(None, envelope)
    timings["county_footprint_seconds"] = round(perf_counter() - started, 3)
    footprint_validation = collector.validate_building_footprint_sources(selected, secondary)
    collector.add_aerial_image_fields(selected)
    image_url = selected.get("primary_aerial_image_url")
    if not image_url:
        raise RuntimeError("no imagery URL was produced")
    started = perf_counter()
    with urlopen(
        Request(str(image_url), headers={"User-Agent": "PilotPointIQ-CountyHealth/1.0"}),
        timeout=45,
    ) as response:
        image_bytes = response.read()
        content_type = response.headers.get_content_type()
    timings["imagery_seconds"] = round(perf_counter() - started, 3)
    if not image_bytes.startswith((b"\xff\xd8\xff", b"\x89PNG")):
        raise RuntimeError(f"imagery response was not JPEG/PNG ({content_type})")
    with Image.open(BytesIO(image_bytes)) as image:
        gray = image.convert("L").resize((256, 256))
        statistics = ImageStat.Stat(gray)
        imagery_quality = {
            "width": image.width,
            "height": image.height,
            "brightness": round(float(statistics.mean[0]), 2),
            "contrast": round(float(statistics.stddev[0]), 2),
        }
    if imagery_quality["contrast"] < 3 or not 5 < imagery_quality["brightness"] < 250:
        raise RuntimeError(f"imagery was blank or low contrast: {imagery_quality}")

    started = perf_counter()
    assessor = fetch_assessor_details(county, [parcel_id])
    timings["assessor_seconds"] = round(perf_counter() - started, 3)
    if not assessor.records:
        raise RuntimeError("no assessor-detail record matched the selected parcel")
    warnings = []
    slow_stages = [name for name, seconds in timings.items() if seconds > 20]
    if slow_stages:
        warnings.append("Slow source response: " + ", ".join(slow_stages))
    photo_date = str(selected.get("primary_aerial_photo_date") or "")
    if photo_date[:4].isdigit() and datetime.now().year - int(photo_date[:4]) > 4:
        warnings.append(f"Imagery may be stale ({photo_date}).")
    schema_checks = {
        "parcel_identifier": bool(parcel_id),
        "parcel_geometry": bool(parcel.get("parcel_geometry")),
        "footprint_geometry": bool(selected.get("building_geometry")),
        "footprint_area": bool(selected.get("building_footprint_sqft")),
        "imagery_date": bool(photo_date),
    }
    missing_required = [
        name for name in ("parcel_identifier", "parcel_geometry", "footprint_geometry", "footprint_area")
        if not schema_checks[name]
    ]
    if missing_required:
        raise RuntimeError("required discovery fields are missing: " + ", ".join(missing_required))
    if not schema_checks["imagery_date"]:
        warnings.append("Imagery source did not publish a capture date.")
    return {
        "county": profile.display_name,
        "status": "healthy",
        "address": address,
        "parcel": parcel_id,
        "address_score": score,
        "primary_footprints": len(primary),
        "matched_footprints": len(primary_matches),
        "secondary_footprints": len(secondary),
        "footprint_validation": footprint_validation,
        "imagery_source": selected.get("primary_aerial_source"),
        "imagery_date": selected.get("primary_aerial_photo_date"),
        "imagery_content_type": content_type,
        "imagery_quality": imagery_quality,
        "schema_checks": schema_checks,
        "timings": timings,
        "warnings": warnings,
        "assessor_source_counts": assessor.source_counts,
        "assessor_warnings": assessor.warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pcs-dir", type=Path, default=DEFAULT_PCS_DIR)
    parser.add_argument("--county", choices=tuple(SAMPLE_ADDRESSES), action="append")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict-discrepancies", action="store_true")
    parser.add_argument("--all-samples", action="store_true")
    parser.add_argument("--address", help="Ad hoc sample address; requires exactly one --county")
    parser.add_argument("--notify-pcs", action="store_true")
    parser.add_argument("--cleanup-orphans", action="store_true")
    parser.add_argument("--orphan-retention-days", type=int, default=7)
    args = parser.parse_args()

    sys.path[:0] = [str(PROJECT_DIR), str(args.pcs_dir.expanduser().resolve())]
    import collect_county_buildings_with_parcels as collector
    import roof_intelligence_single_address as single
    from assessor_detail import fetch_assessor_details
    from county_config import COUNTY_PROFILES

    counties = args.county or list(SAMPLE_ADDRESSES)
    if args.address and len(counties) != 1:
        parser.error("--address requires exactly one --county")
    results = []
    for county in counties:
        sample_results = []
        addresses = (args.address,) if args.address else (
            SAMPLE_ADDRESSES[county] if args.all_samples else SAMPLE_ADDRESSES[county][:1]
        )
        for address in addresses:
            try:
                sample = check_county(
                    county, address, collector, single, COUNTY_PROFILES, fetch_assessor_details
                )
                if args.strict_discrepancies and sample["footprint_validation"].get("status") == "discrepancy":
                    sample["status"] = "failed"
                    sample["error"] = "county and Supabase footprints differ by more than 5%"
            except Exception as exc:
                sample = {"status": "failed", "address": address, "error": str(exc)}
            sample_results.append(sample)
        county_status = aggregate_sample_status(sample_results)
        passed_count = sum(sample.get("status") == "healthy" for sample in sample_results)
        results.append(
            {
                "county": COUNTY_PROFILES[county].display_name,
                "status": county_status,
                "error": next((sample.get("error") for sample in sample_results if sample.get("error")), ""),
                "sample_count": len(sample_results),
                "passed_count": passed_count,
                "failed_count": len(sample_results) - passed_count,
                "samples": sample_results,
            }
        )

    overall_status = aggregate_county_status(results)
    payload = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": overall_status,
        "results": results,
    }
    if args.cleanup_orphans:
        payload["orphan_imagery_removed"] = cleanup_orphan_imagery(args.orphan_retention_days)
    output = json.dumps(payload, indent=2)
    print(output)
    if args.output:
        args.output.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output.expanduser().resolve().write_text(output + "\n", encoding="utf-8")
    if args.notify_pcs:
        from roof_intelligence_jobs import RoofIntelligenceJobStore

        RoofIntelligenceJobStore().record_county_health(payload)
    return 1 if overall_status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
