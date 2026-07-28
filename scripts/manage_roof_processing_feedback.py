#!/usr/bin/env python3
"""List, review, and close local future-processing feedback records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from roof_processing_feedback import (
    ProcessingFeedbackError,
    mark_feedback_applied,
    review_feedback,
    save_feedback_record,
    validate_feedback_record,
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_feedback_record(value)
    return value


def _records(directory: Path, status: str | None) -> list[tuple[Path, dict]]:
    results = []
    for path in sorted(directory.glob("*.json")):
        record = _load(path)
        if status is None or record["status"] == status:
            results.append((path, record))
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    listing = subparsers.add_parser("list")
    listing.add_argument("directory", type=Path)
    listing.add_argument("--status", choices=("pending_review", "approved", "rejected", "applied"))

    review = subparsers.add_parser("review")
    review.add_argument("record", type=Path)
    decision = review.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve", action="store_true")
    decision.add_argument("--reject", action="store_true")
    review.add_argument("--reviewed-by", required=True)
    review.add_argument("--note", required=True)

    apply_command = subparsers.add_parser("apply")
    apply_command.add_argument("record", type=Path)
    apply_command.add_argument("--workflow-version", required=True)
    apply_command.add_argument("--artifact", action="append", required=True)
    apply_command.add_argument("--applied-by", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "list":
            for path, record in _records(args.directory, args.status):
                print(
                    json.dumps(
                        {
                            "path": str(path.resolve()),
                            "feedback_id": record["feedback_id"],
                            "status": record["status"],
                            "address": record["property_identity"].get("address"),
                            "comment": record["comment"],
                            "learning_scopes": record["learning_scopes"],
                        },
                        sort_keys=True,
                    )
                )
            return 0

        source = args.record.resolve()
        record = _load(source)
        if args.command == "review":
            updated = review_feedback(
                record,
                approved=args.approve,
                reviewed_by=args.reviewed_by,
                decision_note=args.note,
            )
        else:
            updated = mark_feedback_applied(
                record,
                workflow_version=args.workflow_version,
                artifacts=args.artifact,
                applied_by=args.applied_by,
            )
        saved = save_feedback_record(updated, source.parent)
        print(json.dumps({"path": str(saved), "status": updated["status"]}, sort_keys=True))
        return 0
    except (OSError, ValueError, ProcessingFeedbackError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
