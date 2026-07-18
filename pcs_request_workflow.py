#!/usr/bin/env python3
"""Adapter between PCS property selections and request-time assessor lookups."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from assessor_detail import (
    MAX_IDENTIFIERS_PER_QUERY,
    AssessorDetailResult,
    enrich_report_row,
    fetch_assessor_details,
    normalize_identifier,
)
from county_config import assessor_sources


SELECTION_TYPES = {"address", "map"}


@dataclass(frozen=True)
class SelectedProperty:
    county: str
    parcel_id: str
    address: str = ""


@dataclass(frozen=True)
class PCSReportRequest:
    request_id: str
    selection_type: str
    properties: tuple[SelectedProperty, ...]


def _text(value: object) -> str:
    return str(value or "").strip()


def _county_key(value: object) -> str:
    county = _text(value).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "clearcreek": "clear_creek",
        "clear_creek_county": "clear_creek",
        "broomfield_county": "broomfield",
    }
    return aliases.get(county, county.removesuffix("_county"))


def parse_pcs_request(payload: dict) -> PCSReportRequest:
    """Validate the bounded PCS payload used by both selection workflows."""
    if not isinstance(payload, dict):
        raise ValueError("PCS report request must be a JSON object")

    selection_type = _text(payload.get("selection_type")).lower()
    if selection_type not in SELECTION_TYPES:
        raise ValueError("selection_type must be 'address' or 'map'")

    raw_properties = payload.get("properties")
    if not isinstance(raw_properties, list) or not raw_properties:
        raise ValueError("properties must contain at least one selected parcel")
    if len(raw_properties) > MAX_IDENTIFIERS_PER_QUERY:
        raise ValueError(
            f"PCS requests are limited to {MAX_IDENTIFIERS_PER_QUERY} selected parcels"
        )
    if selection_type == "address" and len(raw_properties) != 1:
        raise ValueError("An address selection must resolve to exactly one parcel")

    properties: list[SelectedProperty] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(raw_properties):
        if not isinstance(item, dict):
            raise ValueError(f"properties[{index}] must be an object")
        county = _county_key(item.get("county"))
        parcel_id = _text(item.get("parcel_id"))
        if not county:
            raise ValueError(f"properties[{index}].county is required")
        if not parcel_id or not normalize_identifier(parcel_id):
            raise ValueError(f"properties[{index}].parcel_id is required")
        # Validate support while parsing so PCS gets an immediate 4xx-style error.
        assessor_sources(county)
        key = (county, normalize_identifier(parcel_id))
        if key in seen:
            continue
        seen.add(key)
        properties.append(
            SelectedProperty(
                county=county,
                parcel_id=parcel_id,
                address=_text(item.get("address")),
            )
        )

    return PCSReportRequest(
        request_id=_text(payload.get("request_id")),
        selection_type=selection_type,
        properties=tuple(properties),
    )


def selected_property_for_row(
    request: PCSReportRequest, county: object, parcel_id: object
) -> SelectedProperty | None:
    county_key = _county_key(county)
    parcel_key = normalize_identifier(parcel_id)
    for selected in request.properties:
        if selected.county == county_key and normalize_identifier(selected.parcel_id) == parcel_key:
            return selected
    return None


def fetch_request_assessor_details(
    request: PCSReportRequest,
) -> dict[tuple[str, str], AssessorDetailResult]:
    """Fetch each selected parcel independently to prevent cross-parcel merging."""
    results: dict[tuple[str, str], AssessorDetailResult] = {}
    for selected in request.properties:
        results[(selected.county, normalize_identifier(selected.parcel_id))] = (
            fetch_assessor_details(selected.county, [selected.parcel_id])
        )
    return results


def apply_assessor_result_to_row(row: dict, result: AssessorDetailResult) -> None:
    """Fill missing report fields and retain traceability for the manifest."""
    enrich_report_row(row, result)
    row["_assessor_result"] = result


def selected_keys(request: PCSReportRequest) -> set[tuple[str, str]]:
    return {
        (selected.county, normalize_identifier(selected.parcel_id))
        for selected in request.properties
    }


def filter_selected_rows(
    rows: Iterable[dict], request: PCSReportRequest, county_field: str = "County",
    parcel_field: str = "Parcel Number",
) -> list[dict]:
    keys = selected_keys(request)
    selected: list[dict] = []
    for row in rows:
        parcel_key = normalize_identifier(row.get(parcel_field))
        county_key = _county_key(row.get(county_field))
        if county_key and (county_key, parcel_key) in keys:
            selected.append(row)
            continue
        # Some PCS-created one-property CSVs omit County because it is supplied
        # in the request envelope. Permit that only when the parcel is unique.
        parcel_matches = [key for key in keys if key[1] == parcel_key]
        if not county_key and len(parcel_matches) == 1:
            row[county_field] = parcel_matches[0][0].replace("_", " ").title()
            selected.append(row)
    return selected


__all__ = [
    "PCSReportRequest",
    "SelectedProperty",
    "apply_assessor_result_to_row",
    "fetch_request_assessor_details",
    "filter_selected_rows",
    "parse_pcs_request",
    "selected_property_for_row",
]
