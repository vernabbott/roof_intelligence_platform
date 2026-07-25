#!/usr/bin/env python3
"""Regenerate one immutable report revision without rerunning GIS or AI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from render_roof_intelligence_snapshot import render_snapshot
from roof_intelligence_snapshot import (
    create_manual_revision,
    refresh_recommendation,
    validate_snapshot,
)


def regenerate_revision(
    parent_snapshot: Mapping[str, Any],
    edits: Mapping[str, Any],
    *,
    created_by: str,
    change_reason: str,
    output_path: Path,
    report_image: Path | None = None,
    apply_square_footage_to_future: bool = False,
) -> dict[str, Any]:
    """Create, render, verify, and return the next complete revision snapshot."""
    revised = create_manual_revision(
        parent_snapshot,
        edits,
        created_by=created_by,
        change_reason=change_reason,
        apply_square_footage_to_future=apply_square_footage_to_future,
        recommendation_refresher=refresh_recommendation,
    )
    validate_snapshot(revised)

    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{revised['snapshot_id']}.generating")
    try:
        render_snapshot(revised, temporary, report_image)
        if not temporary.is_file() or temporary.stat().st_size <= 1_000:
            raise RuntimeError("Generated revision PDF is missing or unexpectedly small")
        with temporary.open("rb") as handle:
            header = handle.read(4)
        if header != b"%PDF":
            raise RuntimeError("Generated revision is not a PDF")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()

    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "snapshot": revised,
        "report_path": str(target),
        "pdf_size": target.stat().st_size,
        "pdf_checksum": digest.hexdigest(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parent_snapshot", type=Path)
    parser.add_argument("edits", type=Path)
    parser.add_argument("output_pdf", type=Path)
    parser.add_argument("output_snapshot", type=Path)
    parser.add_argument("--created-by", required=True)
    parser.add_argument("--change-reason", required=True)
    parser.add_argument("--report-image", type=Path)
    parser.add_argument("--apply-square-footage-to-future", action="store_true")
    return parser.parse_args()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def main() -> int:
    args = parse_args()
    result = regenerate_revision(
        _load_object(args.parent_snapshot, "Parent snapshot"),
        _load_object(args.edits, "Edits"),
        created_by=args.created_by,
        change_reason=args.change_reason,
        output_path=args.output_pdf,
        report_image=args.report_image,
        apply_square_footage_to_future=args.apply_square_footage_to_future,
    )
    args.output_snapshot.parent.mkdir(parents=True, exist_ok=True)
    args.output_snapshot.write_text(
        json.dumps(result["snapshot"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "snapshot_path": str(args.output_snapshot.resolve()),
                "report_path": result["report_path"],
                "pdf_size": result["pdf_size"],
                "pdf_checksum": result["pdf_checksum"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
