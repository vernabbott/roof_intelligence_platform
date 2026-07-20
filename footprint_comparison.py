"""Shared rules for comparing Microsoft and county footprint areas."""

from __future__ import annotations


def _positive_area(value: object, name: str) -> float:
    try:
        area = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc

    if area <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return area


def compare_microsoft_to_county(
    microsoft_sqft: object,
    county_sqft: object,
    tolerance: float = 0.05,
) -> dict:
    """Flag only when county exceeds Microsoft by more than the tolerance."""

    microsoft_area = _positive_area(microsoft_sqft, "microsoft_sqft")
    county_area = _positive_area(county_sqft, "county_sqft")

    if tolerance < 0:
        raise ValueError("tolerance cannot be negative")

    county_excess = (county_area - microsoft_area) / microsoft_area
    discrepancy = county_excess > tolerance

    result = {
        "status": "discrepancy" if discrepancy else "validated",
        "microsoft_sqft": round(microsoft_area, 1),
        "county_sqft": round(county_area, 1),
        "difference_pct": round(abs(county_excess) * 100, 2),
        "county_excess_pct": round(max(county_excess, 0.0) * 100, 2),
        "tolerance_pct": round(tolerance * 100, 2),
        "comparison_rule": "county_exceeds_microsoft",
    }

    if not discrepancy:
        result["resolution"] = "microsoft_preferred"

    return result