#!/usr/bin/env python3
"""Render a validated Report Snapshot v1 without refreshing data or running AI.

This standalone preparation command is not called by the current PCS or
PilotPoint report workflow.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import generate_roof_intelligence_reports as reports
from roof_intelligence_snapshot import snapshot_to_renderer_inputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render one Report Snapshot v1 PDF.")
    parser.add_argument("snapshot", type=Path, help="Report Snapshot v1 JSON file")
    parser.add_argument("output", type=Path, help="Output PDF path")
    parser.add_argument(
        "--report-image",
        type=Path,
        default=None,
        help="Local copy of the report image referenced by the snapshot",
    )
    return parser.parse_args()


def load_snapshot(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Report snapshot must contain a JSON object")
    return value


def render_snapshot(snapshot: dict, output_path: Path, report_image: Path | None = None) -> None:
    row, analysis = snapshot_to_renderer_inputs(snapshot)
    if report_image is not None and not report_image.is_file():
        raise FileNotFoundError(f"Report image is not available: {report_image}")
    reports.render_report(row, analysis, report_image, None, output_path)


def main() -> int:
    args = parse_args()
    render_snapshot(load_snapshot(args.snapshot), args.output, args.report_image)
    print(json.dumps({"report_path": str(args.output.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
