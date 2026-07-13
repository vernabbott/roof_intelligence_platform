#!/usr/bin/env python3
# © PilotPoint IQ Roof Intelligence All rights reserved
"""Organize canonical source/cache data by county."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent

ZIP_TO_COUNTY = {
    "80033": "Jefferson",
    "80112": "Arapahoe",
    "80223": "Denver",
}


def county_from_csv_name(path: Path) -> str | None:
    name = path.name.lower()
    if name.startswith("arapahoe"):
        return "Arapahoe"
    if name.startswith("jefferson"):
        return "Jefferson"
    if name.startswith("denver") or name.startswith("colorado_parcel_data"):
        return "Denver"
    return None


def data_dirs(county: str) -> dict[str, Path]:
    base = ROOT / "data" / "CO" / county
    dirs = {
        "parcels": base / "parcels",
        "aerial": base / "aerial_imagery",
        "json": base / "json",
    }
    for directory in dirs.values():
        directory.mkdir(parents=True, exist_ok=True)
    return dirs


def replace_file(source: Path, destination: Path) -> bool:
    if source.resolve() == destination.resolve():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    os.replace(source, destination)
    return True


def copy_file(source: Path, destination: Path) -> bool:
    if source.resolve() == destination.resolve():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def move_root_csvs() -> int:
    moved = 0
    for path in sorted(ROOT.glob("*.csv")):
        county = county_from_csv_name(path)
        if not county:
            continue
        target = data_dirs(county)["parcels"] / path.name
        if replace_file(path, target):
            moved += 1
    return moved


def copy_zip_json_to_county_data() -> int:
    copied = 0
    for zip_code, county in ZIP_TO_COUNTY.items():
        source_dir = ROOT / "CO" / zip_code / "json"
        if not source_dir.exists():
            continue
        target_dir = data_dirs(county)["json"]
        for path in sorted(source_dir.glob("*.json")):
            if copy_file(path, target_dir / path.name):
                copied += 1
    return copied


def copy_zip_aerials_to_county_data() -> int:
    copied = 0
    for zip_code, county in ZIP_TO_COUNTY.items():
        source_dir = ROOT / "CO" / zip_code / "Aerial Imagery"
        if not source_dir.exists():
            continue
        target_dir = data_dirs(county)["aerial"]
        for path in sorted(source_dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            if copy_file(path, target_dir / path.name):
                copied += 1
    return copied


def main() -> int:
    print(f"Moved root CSV/parcels files: {move_root_csvs()}")
    print(f"Copied ZIP JSON files into county data: {copy_zip_json_to_county_data()}")
    print(f"Copied ZIP aerial images into county data: {copy_zip_aerials_to_county_data()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# © PilotPoint IQ Roof Intelligence All rights reserved
