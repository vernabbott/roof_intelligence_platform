#!/usr/bin/env python3
# © PilotPoint IQ Roof Intelligence All rights reserved
"""Reorganize existing report outputs into State/ZIP folders."""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STATE_FALLBACK = "CO"


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def safe_path_part(value: object, fallback: str) -> str:
    text = normalize_text(value)
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", " ") else "-" for ch in text).strip()
    cleaned = "-".join(cleaned.split())
    return cleaned or fallback


def zip_code(value: object) -> str:
    digits = "".join(ch for ch in normalize_text(value) if ch.isdigit())
    return digits[:5] if digits else "Unknown-ZIP"


def parcel_from_name(path: Path) -> str:
    name = path.stem
    match = re.match(r"^(?:openai|fallback)-(.+)$", name)
    if match:
        name = match.group(1)
    return name.split("-", 1)[0]


def report_stem(row: dict, fallback: str) -> str:
    parcel = safe_path_part(row.get("Parcel Number"), fallback)
    address = safe_path_part(normalize_text(row.get("Address")).lower(), "roof-report")
    return f"{parcel}-{address}"


def output_dirs(row: dict) -> dict[str, Path]:
    state = safe_path_part(row.get("Building State") or STATE_FALLBACK, "Unknown-State").upper()
    zcode = zip_code(row.get("Building ZIP"))
    base = ROOT / state / zcode
    dirs = {
        "reports": base / "Reports",
        "aerial": base / "Aerial Imagery",
        "json": base / "json",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def load_rows() -> dict[str, dict]:
    rows_by_parcel: dict[str, dict] = {}
    csv.field_size_limit(1024 * 1024 * 1024)
    for csv_path in sorted(ROOT.glob("*.csv")):
        try:
            with csv_path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    parcel = normalize_text(row.get("Parcel Number"))
                    if not parcel or not normalize_text(row.get("Building ZIP")):
                        continue
                    rows_by_parcel[parcel] = row
        except Exception as exc:
            print(f"Skipped CSV {csv_path.name}: {exc}")
    return rows_by_parcel


def replace_with_newer(source: Path, destination: Path) -> bool:
    if source.resolve() == destination.resolve():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    os.replace(source, destination)
    return True


def move_pdfs(rows_by_parcel: dict[str, dict]) -> int:
    moved = 0
    pdfs = [
        path
        for path in ROOT.rglob("*.pdf")
        if path.relative_to(ROOT).parts[:1] != ("CO",)
    ]
    for path in sorted(pdfs, key=lambda item: item.stat().st_mtime):
        parcel = parcel_from_name(path)
        row = rows_by_parcel.get(parcel)
        if not row:
            continue
        target = output_dirs(row)["reports"] / f"{report_stem(row, parcel)}.pdf"
        if replace_with_newer(path, target):
            moved += 1
    return moved


def move_json(rows_by_parcel: dict[str, dict]) -> int:
    moved = 0
    json_files = [
        path
        for path in ROOT.rglob("*.json")
        if path.relative_to(ROOT).parts[:1] != ("CO",)
    ]
    for path in sorted(json_files, key=lambda item: item.stat().st_mtime):
        parcel = parcel_from_name(path)
        row = rows_by_parcel.get(parcel)
        if not row:
            continue
        target = output_dirs(row)["json"] / path.name
        if replace_with_newer(path, target):
            moved += 1
    return moved


def move_images(rows_by_parcel: dict[str, dict]) -> int:
    moved = 0
    extensions = {".jpg", ".jpeg", ".png", ".webp"}
    image_files = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        parts = path.relative_to(ROOT).parts
        if not parts or parts[0] in {"CO", "public", "tmp"}:
            continue
        if not (parts[0].startswith("aerial_images") or "Aerial Imagery" in parts):
            continue
        image_files.append(path)

    for path in sorted(image_files, key=lambda item: item.stat().st_mtime):
        parcel = parcel_from_name(path)
        row = rows_by_parcel.get(parcel)
        if not row:
            continue
        target = output_dirs(row)["aerial"] / path.name
        if replace_with_newer(path, target):
            moved += 1
    return moved


def remove_empty_old_dirs() -> int:
    removed = 0
    candidates = [
        path
        for path in ROOT.iterdir()
        if path.is_dir()
        and (
            path.name.startswith("roof_intelligence_reports")
            or path.name.startswith("roof_ai_analysis_cache")
            or path.name.startswith("aerial_images")
            or path.name == "organized_output_check"
        )
    ]
    for base in candidates:
        for ds_store in base.rglob(".DS_Store"):
            try:
                ds_store.unlink()
            except OSError:
                pass
        for path in sorted(base.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.is_dir():
                try:
                    path.rmdir()
                    removed += 1
                except OSError:
                    pass
        try:
            base.rmdir()
            removed += 1
        except OSError:
            pass
    return removed


def main() -> int:
    rows_by_parcel = load_rows()
    print(f"Loaded row metadata for {len(rows_by_parcel)} parcels")
    print(f"Moved PDFs: {move_pdfs(rows_by_parcel)}")
    print(f"Moved JSON files: {move_json(rows_by_parcel)}")
    print(f"Moved aerial images: {move_images(rows_by_parcel)}")
    print(f"Removed empty old directories: {remove_empty_old_dirs()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# © PilotPoint IQ Roof Intelligence All rights reserved
