#!/usr/bin/env python3
"""List or resolve canonical footprint discrepancies before report creation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from building_footprint_store import list_pending_canonical_footprints, resolve_canonical_footprint


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--county")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--resolve", type=int, metavar="CANONICAL_ID")
    parser.add_argument("--source", choices=("microsoft", "county"))
    parser.add_argument("--reason")
    parser.add_argument("--reviewer")
    args = parser.parse_args()
    if args.resolve is not None:
        if not all((args.source, args.reason, args.reviewer)):
            parser.error("--resolve requires --source, --reason, and --reviewer")
        result = resolve_canonical_footprint(
            args.resolve, args.source, args.reason, args.reviewer
        )
        print(json.dumps(result, default=str, indent=2))
        return 0
    print(json.dumps(list_pending_canonical_footprints(args.county, args.limit), default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
