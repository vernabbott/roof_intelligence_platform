#!/usr/bin/env python3
"""Request-time county assessor detail lookups for selected parcels."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from county_config import AssessorSource, assessor_sources


REQUEST_TIMEOUT_SECONDS = 60
MAX_IDENTIFIERS_PER_QUERY = 100


@dataclass
class AssessorDetailResult:
    county: str
    requested_parcels: list[str]
    records: list[dict] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)
    detail_links: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def normalize_identifier(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def unique_values(values: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        normalized = normalize_identifier(text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(text)
    return result


def _json_request(url: str, *, params: dict | None = None, payload: dict | None = None) -> dict:
    if params:
        url = url + ("&" if "?" in url else "?") + urlencode(params)
    data = None
    headers = {"User-Agent": "PilotPointIQ-AssessorLookup/1.0", "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        result = json.load(response)
    if isinstance(result, dict) and result.get("error"):
        raise RuntimeError(f"Assessor service error: {result['error']}")
    return result


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _identifier_variants(
    values: Iterable[str], groupings: tuple[tuple[int, ...], ...] = ()
) -> list[str]:
    variants: list[str] = []
    seen: set[str] = set()
    for value in values:
        for variant in (str(value).strip(), normalize_identifier(value)):
            if not variant or variant in seen:
                continue
            seen.add(variant)
            variants.append(variant)
        normalized = normalize_identifier(value)
        for grouping in groupings:
            if sum(grouping) != len(normalized):
                continue
            parts: list[str] = []
            offset = 0
            for width in grouping:
                parts.append(normalized[offset : offset + width])
                offset += width
            grouped = "-".join(parts)
            if grouped not in seen:
                seen.add(grouped)
                variants.append(grouped)
    return variants


def query_arcgis_source(source: AssessorSource, identifiers: Iterable[str]) -> list[dict]:
    """Query an ArcGIS assessor table by exact parcel or account identifiers."""
    values = _identifier_variants(identifiers, source.identifier_groupings)
    if not values:
        return []
    if len(values) > MAX_IDENTIFIERS_PER_QUERY:
        raise ValueError(f"Assessor lookup is limited to {MAX_IDENTIFIERS_PER_QUERY} identifiers per request")
    if not source.lookup_field:
        raise ValueError(f"ArcGIS source {source.key} does not define a lookup field")
    value_list = ",".join(_sql_literal(value) for value in values)
    lookup_fields = (source.lookup_field, *source.alternate_lookup_fields)
    clauses = [f"{field_name} IN ({value_list})" for field_name in lookup_fields]
    where = clauses[0] if len(clauses) == 1 else "(" + " OR ".join(clauses) + ")"
    result = _json_request(
        source.url,
        params={
            "where": where,
            "outFields": "*",
            "returnGeometry": "false",
            "resultRecordCount": "2000",
            "f": "json",
        },
    )
    return [feature.get("attributes", {}) for feature in result.get("features", [])]


def query_douglas_source(source: AssessorSource, identifiers: Iterable[str]) -> list[dict]:
    values = [normalize_identifier(value).lower() for value in identifiers if normalize_identifier(value)]
    if not values:
        return []
    result = _json_request(
        source.url,
        payload={"query": {"bool": {"filter": [{"terms": {source.lookup_field: values}}]}}},
    )
    return [hit.get("_source", {}) for hit in result.get("hits", {}).get("hits", [])]


def query_larimer_source(source: AssessorSource, identifiers: Iterable[str]) -> list[dict]:
    records: list[dict] = []
    for identifier in unique_values(identifiers):
        if source.lookup_by == "parcel":
            result = _json_request(source.url, params={"prop": "property", "parcel": identifier})
            records.extend(result.get("records") or [])
            continue
        for resource in ("detail", "improvement", "valuedetail"):
            try:
                result = _json_request(source.url, params={"prop": resource, "accountno": identifier})
            except Exception:
                # Some resources do not apply to personal/mobile accounts that
                # share a parcel with a real-property account.
                continue
            for record in result.get("records") or []:
                tagged = dict(record)
                tagged["_larimer_resource"] = resource
                records.append(tagged)
    return records


def query_source(source: AssessorSource, identifiers: Iterable[str]) -> list[dict]:
    if source.kind == "arcgis":
        return query_arcgis_source(source, identifiers)
    if source.kind == "elasticsearch_proxy":
        return query_douglas_source(source, identifiers)
    if source.kind == "larimer_json":
        return query_larimer_source(source, identifiers)
    raise ValueError(f"Unsupported assessor source kind: {source.kind}")


def _collect_identifiers(records: Iterable[dict], fields: Iterable[str]) -> list[str]:
    return unique_values(record.get(name) for record in records for name in fields)


def fetch_assessor_details(county: str, parcel_ids: Iterable[object]) -> AssessorDetailResult:
    """Fetch assessor records for exact parcel IDs without a county-wide scan."""
    parcels = unique_values(parcel_ids)
    if not parcels:
        raise ValueError("At least one parcel identifier is required")
    if len(parcels) > MAX_IDENTIFIERS_PER_QUERY:
        raise ValueError(f"Assessor lookup is limited to {MAX_IDENTIFIERS_PER_QUERY} parcels per request")

    result = AssessorDetailResult(county=county, requested_parcels=parcels)
    identifiers = {"parcel": list(parcels), "account": []}

    for source in assessor_sources(county):
        source_values = identifiers[source.lookup_by]
        if source.kind == "html_detail":
            for account in source_values:
                result.detail_links.append(source.url.format(account=account))
            if source_values:
                result.warnings.append(f"{source.label} is available as a detail-page fallback")
            continue
        if not source_values:
            result.source_counts[source.key] = 0
            continue
        try:
            records = query_source(source, source_values)
        except Exception as exc:
            result.source_counts[source.key] = 0
            result.warnings.append(f"{source.label} lookup failed: {exc}")
            continue

        tagged_records: list[dict] = []
        for record in records:
            tagged = dict(record)
            tagged["_assessor_source"] = source.key
            tagged["_assessor_role"] = source.role
            tagged_records.append(tagged)
        result.records.extend(tagged_records)
        result.source_counts[source.key] = len(tagged_records)
        identifiers["parcel"] = unique_values(
            [*identifiers["parcel"], *_collect_identifiers(records, source.parcel_fields)]
        )
        identifiers["account"] = unique_values(
            [*identifiers["account"], *_collect_identifiers(records, source.account_fields)]
        )

    if not result.records:
        result.warnings.append("No assessor records were returned for the requested parcel identifiers")
    return result


CANONICAL_REPORT_FIELDS: dict[str, tuple[str, ...]] = {
    "Year Built": (
        "yearbuilt", "actualyearbuilt", "year_built", "origyoc", "orig_year_built",
        "comorigyearbuilt", "resorigyearbuilt", "sttyrblt",
    ),
    "Effective Year Built": (
        "effectiveyearbuilt", "effyearbuilt", "effyrbuilt", "effyoc", "remodelyear",
        "remodel",
    ),
    "Property Use": (
        "primarybltasdescription", "propertytype", "property_type", "propertyclassdesc",
        "classcodedescr", "designdscr", "areadscr", "occdesc", "occcodedescription1",
        "comstructuretype", "bldgtype", "stttypuse",
    ),
    "Stories": (
        "stories", "numberofstories", "numstories", "nostories", "nofloors", "sttnbrflr",
    ),
    "Construction Type": (
        "constructiontype", "structuretype", "comstructuretype", "classdesc", "bldgtype",
        "stttypcns",
    ),
    "Land Value": (
        "landvalue", "appraisedlandvalue", "asmtapprland", "apprlandloc", "totactlndv",
    ),
}

EXPLICIT_FOOTPRINT_FIELDS = {
    "buildingfootprint",
    "buildingfootprintsqft",
    "footprintarea",
    "footprintsqft",
    "groundfloorarea",
    "groundfloorsqft",
}


def _normalized_record_values(value: object) -> Iterable[tuple[str, object]]:
    if isinstance(value, dict):
        for key, item in value.items():
            if item not in (None, "", 0, "0"):
                yield normalize_identifier(key).lower(), item
            yield from _normalized_record_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _normalized_record_values(item)


def canonical_report_values(records: Iterable[dict]) -> dict[str, object]:
    """Extract conservative, report-safe fields from heterogeneous assessor records."""
    values = list(_normalized_record_values(list(records)))
    output: dict[str, object] = {}
    for report_field, candidates in CANONICAL_REPORT_FIELDS.items():
        candidate_keys = {normalize_identifier(candidate).lower() for candidate in candidates}
        for key, value in values:
            if key in candidate_keys and not isinstance(value, (dict, list)):
                output[report_field] = value
                break
    return output


def validate_assessor_footprint(
    footprint_sqft: object,
    records: Iterable[dict],
    tolerance: float = 0.05,
) -> dict:
    """Compare only assessor fields that explicitly represent ground footprint area."""
    try:
        primary_area = float(footprint_sqft or 0)
    except (TypeError, ValueError):
        primary_area = 0.0
    record_list = list(records)
    if primary_area <= 0:
        return {"status": "footprint_unavailable"}
    if not record_list:
        return {"status": "assessor_unavailable", "primary_sqft": round(primary_area, 1)}

    candidates: list[tuple[str, float]] = []
    for key, value in _normalized_record_values(record_list):
        if key not in EXPLICIT_FOOTPRINT_FIELDS or isinstance(value, (dict, list)):
            continue
        try:
            area = float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            continue
        if area > 0 and not any(abs(area - existing) < 0.01 for _, existing in candidates):
            candidates.append((key, area))
    if not candidates:
        return {
            "status": "not_comparable",
            "primary_sqft": round(primary_area, 1),
            "reason": (
                "Assessor records did not publish an explicit building-footprint or "
                "ground-floor-area field; gross, finished, total and living areas were not compared."
            ),
        }
    if len(candidates) != 1:
        return {
            "status": "not_comparable",
            "primary_sqft": round(primary_area, 1),
            "reason": "Assessor records returned multiple explicit footprint areas that could not be tied to one selected structure.",
        }

    field_name, assessor_area = candidates[0]
    difference = abs(primary_area - assessor_area) / max(primary_area, 1.0)
    return {
        "status": "validated" if difference <= tolerance else "discrepancy",
        "field": field_name,
        "primary_sqft": round(primary_area, 1),
        "assessor_sqft": round(assessor_area, 1),
        "difference_pct": round(difference * 100, 2),
        "tolerance_pct": round(tolerance * 100, 2),
    }


def enrich_report_row(row: dict, result: AssessorDetailResult) -> dict:
    """Fill blank canonical fields and attach assessor traceability metadata."""
    for field_name, value in canonical_report_values(result.records).items():
        if row.get(field_name) in (None, "", 0, "0"):
            row[field_name] = value
    row["Assessor Data Sources"] = ", ".join(
        key for key, count in result.source_counts.items() if count
    )
    row["Assessor Detail Links"] = ", ".join(result.detail_links)
    row["Assessor Data Warnings"] = " | ".join(result.warnings)
    row["Assessor Record Count"] = len(result.records)
    return row


__all__ = [
    "AssessorDetailResult",
    "MAX_IDENTIFIERS_PER_QUERY",
    "fetch_assessor_details",
    "canonical_report_values",
    "enrich_report_row",
    "normalize_identifier",
    "query_arcgis_source",
    "validate_assessor_footprint",
]
