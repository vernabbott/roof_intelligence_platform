#!/usr/bin/env python3
# © PilotPoint IQ Roof Intelligence All rights reserved
"""Backfill aerial imagery QA columns in an existing collection CSV."""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

from collect_denver_buildings_with_parcels import image_qa


QA_COLUMNS = [
    "Primary Aerial QA Status",
    "Primary Aerial QA Reason",
    "Primary Aerial QA Blank",
    "Primary Aerial QA Width",
    "Primary Aerial QA Height",
    "Primary Aerial QA Brightness",
    "Primary Aerial QA Contrast",
]


def resolve_path(base_dir: Path, value: str) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    if path.exists():
        return path

    file_name = Path(value).name
    if not file_name:
        return None
    for root_name in ("data", "CO"):
        search_root = base_dir / root_name
        if not search_root.exists():
            continue
        for candidate in search_root.rglob(file_name):
            if candidate.is_file():
                return candidate
    return path


def resolve_image_path(base_dir: Path, row: dict) -> Path | None:
    path = resolve_path(base_dir, row.get("Primary Aerial Image File", ""))
    if path and path.exists():
        return path

    parcel = "".join(ch for ch in str(row.get("Parcel Number") or "") if ch.isalnum())
    if not parcel:
        return path
    for root_name in ("CO", "data"):
        search_root = base_dir / root_name
        if not search_root.exists():
            continue
        for candidate in search_root.rglob(f"{parcel}-*"):
            if candidate.is_file() and candidate.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}:
                return candidate
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill primary aerial imagery QA columns in a CSV.")
    parser.add_argument("csv_path", help="CSV file to update")
    parser.add_argument("--in-place", action="store_true", help="Replace the CSV after writing a .bak backup")
    parser.add_argument("--output", default=None, help="Output CSV path; defaults to <input>_with_qa.csv unless --in-place is used")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = Path.cwd()
    input_path = Path(args.csv_path)
    if not input_path.is_absolute():
        input_path = base_dir / input_path

    with input_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    for column in QA_COLUMNS:
        if column not in fieldnames:
            fieldnames.append(column)

    for row in rows:
        image_path = resolve_image_path(base_dir, row)
        qa = image_qa(str(image_path) if image_path else None)
        row["Primary Aerial QA Status"] = qa["status"]
        row["Primary Aerial QA Reason"] = qa["reason"]
        row["Primary Aerial QA Blank"] = qa["blank"]
        row["Primary Aerial QA Width"] = qa["width"]
        row["Primary Aerial QA Height"] = qa["height"]
        row["Primary Aerial QA Brightness"] = qa["brightness"]
        row["Primary Aerial QA Contrast"] = qa["contrast"]

    if args.in_place:
        output_path = input_path
        backup_path = input_path.with_suffix(input_path.suffix + ".bak")
        shutil.copy2(input_path, backup_path)
        print(f"Wrote backup {backup_path}")
    else:
        output_path = Path(args.output) if args.output else input_path.with_name(f"{input_path.stem}_with_qa{input_path.suffix}")
        if not output_path.is_absolute():
            output_path = base_dir / output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# © PilotPoint IQ Roof Intelligence All rights reserved
