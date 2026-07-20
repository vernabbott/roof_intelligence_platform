#!/usr/bin/env python3
"""Compatibility alias for the county-neutral collector.

New code must import ``collect_county_buildings_with_parcels``.
"""

from __future__ import annotations

import sys

import collect_county_buildings_with_parcels as _collector


if __name__ == "__main__":
    raise SystemExit(
        "The retired ZIP/CSV collector is no longer executable. "
        "Use the PCS single-address, rectangle, or radius workflow."
    )

# Preserve old imports without maintaining a second implementation or a
# separate set of mutable county configuration globals.
sys.modules[__name__] = _collector
