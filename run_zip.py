#!/usr/bin/env python3
# © PilotPoint IQ Roof Intelligence All rights reserved
"""Run a county/ZIP roof intelligence collection and report generation job."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from county_config import county_profile


def normalize_zip(value: object) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 5:
        raise ValueError(f"ZIP code must contain at least 5 digits: {value}")
    return digits[:5]


def county_folder_name(display_name: str) -> str:
    return display_name.replace(" County", "").replace(" ", "")


def run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess:
    print("Running:", " ".join(command))
    return subprocess.run(command, cwd=cwd, text=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run collection and report generation for one ZIP code.")
    parser.add_argument("--state", default="CO", help="Two-letter state code")
    parser.add_argument("--county", required=True, help="County profile key, such as adams, arapahoe, or jefferson")
    parser.add_argument("--zip", required=True, dest="zip_code", help="Five-digit ZIP code")
    parser.add_argument("--input", default=None, help="Existing CSV to use when skipping collection")
    parser.add_argument("--limit", type=int, default=None, help="Maximum output records/reports for this ZIP run")
    parser.add_argument("--building-limit", type=int, default=None, help="Maximum raw building records to fetch")
    parser.add_argument("--parcel-limit", type=int, default=None, help="Maximum parcel records to fetch")
    parser.add_argument("--min-squares", type=float, default=50.0, help="Minimum roof squares for report candidates")
    parser.add_argument("--refresh-parcel-cache", action="store_true", help="Refresh the ZIP parcel cache")
    parser.add_argument("--parcel-scan-buildings", action="store_true", help="Query roofprints around individual parcels during collection")
    parser.add_argument("--skip-collection", action="store_true", help="Use the existing ZIP CSV and skip collection")
    parser.add_argument("--skip-reports", action="store_true", help="Only collect data; do not generate reports")
    parser.add_argument("--use-ai", action="store_true", help="Use AI vision analysis for report generation")
    parser.add_argument("--ai-provider", choices=("openai", "gemini"), default="openai", help="AI provider")
    parser.add_argument("--ai-model", default=None, help="AI model override")
    parser.add_argument(
        "--roof-reference-classification",
        action="store_true",
        help="Use the feature-flagged two-stage roof-reference classification workflow",
    )
    parser.add_argument("--allow-ai-fallback", action="store_true", help="Continue with fallback reports when AI fails")
    parser.add_argument("--skip-existing-reports", action="store_true", help="Skip PDFs that already exist")
    parser.add_argument("--only-missing", action="store_true", help="Alias for --skip-existing-reports")
    parser.add_argument("--retry-failed-ai", action="store_true", help="Retry existing fallback reports when --use-ai is enabled")
    parser.add_argument("--force", action="store_true", help="Regenerate outputs even when files already exist")
    parser.add_argument("--cleanup-stale-only", action="store_true", help="Only remove stale duplicate files for this ZIP")
    parser.add_argument("--image-format", choices=("jpg", "webp"), default="jpg", help="Downloaded aerial crop format")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root_dir = Path(__file__).resolve().parent
    state = (args.state or "CO").strip().upper()
    zip_code = normalize_zip(args.zip_code)
    profile = county_profile(args.county)
    county_dir = county_folder_name(profile.display_name)

    data_dir = root_dir / "data" / state / county_dir
    parcels_dir = data_dir / "parcels"
    aerial_dir = data_dir / "aerial_imagery"
    deliverable_dir = root_dir / state / zip_code
    output_csv = parcels_dir / f"{profile.key}_{zip_code}_buildings_with_parcels.csv"
    if args.input:
        output_csv = Path(args.input)
        if not output_csv.is_absolute():
            output_csv = root_dir / output_csv
    parcel_cache = parcels_dir / f"{profile.key}_{zip_code}_parcel_data.csv"
    report_manifest = deliverable_dir / "report_manifest.json"
    run_manifest = deliverable_dir / "run_manifest.json"

    deliverable_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "state": state,
        "county": county_dir,
        "county_profile": profile.key,
        "zip_code": zip_code,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "paths": {
            "input_csv": str(output_csv),
            "parcel_cache": str(parcel_cache),
            "aerial_imagery": str(aerial_dir),
            "deliverables": str(deliverable_dir),
            "report_manifest": str(report_manifest),
        },
        "commands": [],
        "status": "running",
    }

    try:
        if not args.skip_collection:
            collect_command = [
                sys.executable,
                "collect_denver_buildings_with_parcels.py",
                "--state",
                state,
                "--county",
                profile.key,
                "--zip-codes",
                zip_code,
                "--output",
                str(output_csv),
                "--parcel-cache",
                str(parcel_cache),
                "--min-squares",
                str(args.min_squares),
                "--download-aerial-images",
                "--image-dir",
                str(aerial_dir),
                "--image-mode",
                "ai-crop",
                "--image-format",
                args.image_format,
            ]
            if args.limit is not None:
                collect_command.extend(["--max-output-records", str(args.limit)])
            if args.building_limit is not None:
                collect_command.extend(["--limit", str(args.building_limit)])
            if args.parcel_limit is not None:
                collect_command.extend(["--parcel-limit", str(args.parcel_limit)])
            if args.refresh_parcel_cache:
                collect_command.append("--refresh-parcel-cache")
            if args.parcel_scan_buildings:
                collect_command.append("--parcel-scan-buildings")
            manifest["commands"].append(collect_command)
            result = run_command(collect_command, root_dir)
            if result.returncode != 0:
                manifest["status"] = "collection_failed"
                return result.returncode

        if not output_csv.exists():
            manifest["status"] = "missing_input_csv"
            print(f"Input CSV not found: {output_csv}")
            return 1

        if not args.skip_reports:
            report_command = [
                sys.executable,
                "generate_roof_intelligence_reports.py",
                "--input",
                str(output_csv),
                "--output-dir",
                str(root_dir),
                "--state",
                state,
                "--county",
                county_dir,
                "--zip-code",
                zip_code,
                "--manifest",
                str(report_manifest),
            ]
            if args.limit is not None:
                report_command.extend(["--limit", str(args.limit)])
            if args.use_ai:
                report_command.append("--use-ai")
            if args.ai_provider:
                report_command.extend(["--ai-provider", args.ai_provider])
            if args.ai_model:
                report_command.extend(["--ai-model", args.ai_model])
            if args.roof_reference_classification:
                report_command.append("--roof-reference-classification")
            if args.allow_ai_fallback:
                report_command.append("--allow-ai-fallback")
            if args.skip_existing_reports:
                report_command.append("--skip-existing-reports")
            if args.only_missing:
                report_command.append("--only-missing")
            if args.retry_failed_ai:
                report_command.append("--retry-failed-ai")
            if args.force:
                report_command.append("--force")
            if args.cleanup_stale_only:
                report_command.append("--cleanup-stale-only")
            manifest["commands"].append(report_command)
            result = run_command(report_command, root_dir)
            if result.returncode != 0:
                manifest["status"] = "report_generation_failed"
                return result.returncode

        if report_manifest.exists():
            manifest["report_summary"] = json.loads(report_manifest.read_text(encoding="utf-8")).get("counts", {})
        manifest["status"] = "complete"
        return 0
    finally:
        manifest["finished_at"] = datetime.now().isoformat(timespec="seconds")
        run_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Wrote run manifest {run_manifest}")


if __name__ == "__main__":
    raise SystemExit(main())

# © PilotPoint IQ Roof Intelligence All rights reserved
