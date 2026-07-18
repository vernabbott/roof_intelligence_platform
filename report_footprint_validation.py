#!/usr/bin/env python3
"""Request-time footprint validation for standalone and bulk report rows."""

from __future__ import annotations

from typing import Any

from pyproj import Transformer
from shapely import wkt
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from county_config import county_profile


TOLERANCE = 0.05


def county_key(value: object) -> str:
    key = str(value or "").strip().lower().replace(" county", "")
    return key.replace("-", "_").replace(" ", "_")


def _wkid(metadata: dict) -> int | None:
    for key in ("latestWkid", "wkid"):
        value = metadata.get(key)
        if value:
            return int(value)
    return None


def _row_polygon_wgs84(row: dict, profile: Any, collector: Any) -> BaseGeometry:
    value = str(row.get("Building Footprint") or "").strip()
    if not value:
        raise RuntimeError("Building footprint geometry is missing from the report row")
    try:
        polygon = wkt.loads(value)
    except Exception as exc:
        raise RuntimeError("Building footprint geometry is not valid WKT") from exc
    if polygon.is_empty:
        raise RuntimeError("Building footprint geometry is empty")
    minx, miny, maxx, maxy = polygon.bounds
    if -180 <= minx <= 180 and -180 <= maxx <= 180 and -90 <= miny <= 90 and -90 <= maxy <= 90:
        return polygon

    metadata = collector.inspect_service_metadata(profile.building_url) if profile.building_url else {}
    source_crs = _wkid(metadata)
    if not source_crs:
        raise RuntimeError(
            f"Cannot determine the coordinate system for the stored {profile.display_name} footprint"
        )
    return transform(Transformer.from_crs(source_crs, 4326, always_xy=True).transform, polygon)


def _configure_collector(collector: Any, profile: Any) -> None:
    collector.DENVER_BUILDINGS_URL = profile.building_url
    collector.PARCELS_URL = profile.parcel_url
    collector.IMAGERY_SOURCES = list(profile.imagery_sources)
    collector.ACTIVE_COUNTY_NAME = profile.display_name.replace(" County", "")
    collector.ACTIVE_STATE = "CO"
    collector.BUILDING_SOURCE_KIND = profile.building_source
    collector._COLLECT_BUILDING_FIELDS = None


def _best_overlap(polygon: BaseGeometry, records: list[dict]) -> dict | None:
    projected = transform(Transformer.from_crs(4326, 26913, always_xy=True).transform, polygon)
    best: tuple[float, dict] | None = None
    for record in records:
        value = str(record.get("building_geometry") or "").strip()
        if not value:
            continue
        try:
            candidate = wkt.loads(value)
            candidate = transform(Transformer.from_crs(4326, 26913, always_xy=True).transform, candidate)
            overlap = projected.intersection(candidate).area
        except Exception:
            continue
        if overlap > 0 and (best is None or overlap > best[0]):
            best = (overlap, record)
    return best[1] if best else None


def _area_comparison(row_area: float, source_area: float, source: str) -> dict:
    difference = abs(row_area - source_area) / max(source_area, 1.0)
    return {
        "status": "validated" if difference <= TOLERANCE else "discrepancy",
        "report_sqft": round(row_area, 1),
        "source_sqft": round(source_area, 1),
        "source": source,
        "difference_pct": round(difference * 100, 2),
        "tolerance_pct": TOLERANCE * 100,
    }


def _number(value: object) -> float:
    try:
        return float(str(value or "").replace(",", "").strip())
    except ValueError:
        return 0.0


def validate_report_row_footprints(row: dict) -> dict:
    """Cross-check one report row against bounded live footprint sources.

    The database and county requests fail independently so either source can
    keep report generation available. A difference over five percent remains
    a hard stop.
    """
    import collect_denver_buildings_with_parcels as collector
    from building_footprint_store import canonical_needs_revalidation, save_canonical_footprint

    key = county_key(row.get("County"))
    if not key:
        raise RuntimeError("County is required for live building-footprint validation")
    profile = county_profile(key)
    _configure_collector(collector, profile)
    polygon = _row_polygon_wgs84(row, profile, collector)
    minx, miny, maxx, maxy = polygon.bounds
    pad = max(maxx - minx, maxy - miny, 0.00005) * 0.15
    envelope = f"{minx - pad},{miny - pad},{maxx + pad},{maxy + pad}"

    primary_error = ""
    county_error = ""
    try:
        primary_records = collector.collect_buildings(100, envelope)
    except Exception as exc:
        primary_records = []
        primary_error = " ".join(str(exc).split())[:300]
    primary = _best_overlap(polygon, primary_records)
    canonical_status = str((primary or {}).get("canonical_status") or "")
    revalidation_due = canonical_needs_revalidation(primary)
    if canonical_status == "pending_review":
        raise RuntimeError(
            f"Building footprint discrepancy needs attention for {profile.display_name} parcel "
            f"{row.get('Parcel Number') or 'unknown'}: canonical footprint "
            f"{primary.get('canonical_id')} is pending review."
        )
    if (
        canonical_status in {"validated", "single_source", "manually_resolved"}
        and not revalidation_due
    ):
        county_records = []
    else:
        try:
            county_records = collector.collect_secondary_buildings(100, envelope)
        except Exception as exc:
            county_records = []
            county_error = " ".join(str(exc).split())[:300]
    county = _best_overlap(polygon, county_records)
    selected = primary or county
    selected_source = "supabase" if primary else "county"
    if not selected:
        details = "; ".join(part for part in (primary_error, county_error) if part)
        raise RuntimeError(
            f"No live building footprint overlaps the report geometry for {profile.display_name}"
            + (f": {details}" if details else "")
        )

    row_area = _number(row.get("Building Footprint Sq Ft"))
    source_area = _number(selected.get("footprint_sqft") or selected.get("building_shape_area"))
    if row_area <= 0 or source_area <= 0:
        raise RuntimeError("Building footprint area is unavailable for live validation")
    row_check = _area_comparison(row_area, source_area, selected_source)
    if row_check["status"] == "discrepancy":
        raise RuntimeError(
            f"Building footprint discrepancy needs attention for {profile.display_name} parcel "
            f"{row.get('Parcel Number') or 'unknown'}: report footprint {row_area:.0f} sq ft versus "
            f"{selected_source} footprint {source_area:.0f} sq ft "
            f"({row_check['difference_pct']:.2f}% difference; 5% allowed)."
        )

    if canonical_status and not revalidation_due:
        source_check = primary.get("canonical_validation") or {"status": canonical_status}
    else:
        source_check = (
            collector.validate_building_footprint_sources(primary, county_records)
            if primary
            else {"status": "county_only", "secondary_sqft": round(source_area, 1)}
        )
    if source_check.get("status") == "discrepancy":
        canonical = save_canonical_footprint(
            profile.display_name,
            str(row.get("Parcel Number") or ""),
            primary,
            county,
            source_check,
            address=str(row.get("Address") or row.get("Property Address") or ""),
        )
        raise RuntimeError(
            f"Building footprint discrepancy needs attention for {profile.display_name} parcel "
            f"{row.get('Parcel Number') or 'unknown'}: Supabase Microsoft footprint "
            f"{source_check['primary_sqft']:.0f} sq ft versus county GIS footprint "
            f"{source_check['secondary_sqft']:.0f} sq ft "
            f"({source_check['difference_pct']:.2f}% difference; 5% allowed)."
        )
    canonical = None
    if not canonical_status or revalidation_due:
        canonical = save_canonical_footprint(
            profile.display_name,
            str(row.get("Parcel Number") or ""),
            primary,
            county,
            source_check,
            address=str(row.get("Address") or row.get("Property Address") or ""),
        )
    warnings: list[str] = []
    if revalidation_due:
        warnings.append(
            "The canonical Microsoft footprint was revalidated because its source data "
            "changed or its 30-day validation window expired."
        )
    if not primary:
        warnings.append(
            "Live footprint validation used only the county GIS source"
            + (f" because Supabase failed: {primary_error}" if primary_error else ".")
        )
    elif source_check.get("status") == "primary_only" and not canonical_status:
        warnings.append(
            "Live footprint validation used only Supabase"
            + (f" because the county lookup failed: {county_error}" if county_error else ".")
        )
    return {
        "status": source_check.get("status"),
        "selected_source": "canonical" if canonical_status else selected_source,
        "row_comparison": row_check,
        "source_comparison": source_check,
        "warnings": warnings,
        "primary_error": primary_error,
        "county_error": county_error,
        "canonical_id": (canonical or primary or {}).get("canonical_id"),
    }


__all__ = ["validate_report_row_footprints"]
