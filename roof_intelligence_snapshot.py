"""Pure Report Snapshot v1 creation and manual-revision calculations.

The generator creates snapshots only when versioned editing is feature-flagged;
the default report workflow remains unchanged.
"""

from __future__ import annotations

from copy import deepcopy
import datetime as dt
import math
from pathlib import Path
from typing import Any, Callable, Mapping
import uuid

from roof_replacement_cost_estimator import (
    COST_ESTIMATION_CONFIG,
    CostConfidenceInputs,
    estimate_roof_coating_cost,
    estimate_roof_replacement_cost,
)
from report_summary_config import REPORT_SUMMARY_CONFIG, finalize_narrative
from roof_assessment import build_consistent_summary, formatted_capture_date


SNAPSHOT_SCHEMA_VERSION = 1
CALCULATION_VERSION = "cost-estimation-v1"
SNAPSHOT_SCHEMA_PATH = (
    Path(__file__).resolve().parent
    / "contracts"
    / "roof_intelligence_report_snapshot_v1.schema.json"
)

EDITABLE_FIELDS = frozenset(
    {
        "roof_area_sqft",
        "roof_type",
        "roof_system",
        "roof_condition_score",
        "report_summary",
        "recommendation",
    }
)


class SnapshotValidationError(ValueError):
    """Raised when a report snapshot or manual edit violates the v1 contract."""


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _nonempty_text(value: object, field: str) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        raise SnapshotValidationError(f"{field} must be non-empty text")
    return text


def _number(value: object, field: str, minimum: float, maximum: float | None = None) -> float:
    if isinstance(value, bool):
        raise SnapshotValidationError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SnapshotValidationError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number < minimum or (maximum is not None and number > maximum):
        limit = f" between {minimum:g} and {maximum:g}" if maximum is not None else f" at least {minimum:g}"
        raise SnapshotValidationError(f"{field} must be{limit}")
    return number


def condition_label_for_score(score: float) -> str:
    if score >= 80:
        return "GOOD"
    if score >= 60:
        return "FAIR"
    return "POOR"


def risk_level_for_score(score: float) -> str:
    if score >= 80:
        return "LOW"
    if score >= 60:
        return "MODERATE"
    return "HIGH"


def refresh_recommendation(snapshot: Mapping[str, Any]) -> str:
    """Create a deterministic recommendation aligned to edited roof facts."""
    analysis = snapshot.get("analysis") or {}
    calculations = snapshot.get("calculations") or {}
    roof_type = _nonempty_text(analysis.get("roof_type") or "the identified roof", "roof_type")
    roof_system = _nonempty_text(analysis.get("roof_system") or roof_type, "roof_system")
    recommendation_roof_type = roof_type
    if recommendation_roof_type.lower().startswith("primary:"):
        recommendation_roof_type = recommendation_roof_type.split(":", 1)[1].strip()
    recommendation_roof_type = recommendation_roof_type.replace(
        "; Secondary:",
        ", with secondary",
    )
    condition = str(calculations.get("condition_label") or "FAIR").strip().lower()
    score = _number(analysis.get("overall_score"), "roof_condition_score", 0, 100)

    if condition == "good":
        direction = (
            "Prioritize preventive maintenance and verify whether a compatible restoration "
            "coating can extend service life before considering replacement."
        )
    elif condition == "fair":
        direction = (
            "Evaluate targeted repairs and a compatible restoration coating before committing "
            "to an overlay or complete replacement."
        )
    else:
        direction = (
            "Arrange a near-term field assessment and compare necessary repairs, restoration, "
            "overlay, and replacement based on confirmed substrate and moisture conditions."
        )
    return (
        f"The revised assessment identifies roof type {recommendation_roof_type} and physical configuration "
        f"{roof_system}, with a condition score "
        f"of {score:g}/100 ({condition}). {direction} Have a qualified commercial roofing "
        "contractor verify the assembly, drainage, moisture condition, and manufacturer "
        "requirements before selecting a scope."
    )


def calculate_report_values(
    roof_area_sqft: object,
    roof_condition_score: object,
    confidence_inputs: CostConfidenceInputs | None = None,
) -> dict[str, Any]:
    """Apply the existing fixed formulas to editable area and score inputs."""
    area = _number(roof_area_sqft, "roof_area_sqft", 0)
    score = _number(roof_condition_score, "roof_condition_score", 0, 100)
    replacement = estimate_roof_replacement_cost(
        roof_condition_score=score,
        roof_area_sqft=area,
        confidence_inputs=confidence_inputs,
    ).to_dict()
    coating = estimate_roof_coating_cost(area).to_dict()
    # Snapshots are persisted as JSON. ``dataclasses.asdict`` preserves the
    # estimator's tuple here, while a JSON round trip restores it as a list.
    # Keep calculated values JSON-native so an unchanged stored snapshot
    # validates identically when it is used as the parent of a revision.
    coating["warranty_options"] = list(coating["warranty_options"])
    roof_squares = round(int(area) / 100) if area else 0
    return {
        "calculation_version": CALCULATION_VERSION,
        "roof_area_sqft": area,
        "roof_squares": roof_squares,
        "roof_condition_score": score,
        "condition_label": condition_label_for_score(score),
        "risk_level": risk_level_for_score(score),
        "replacement": {
            "cost_per_sqft": replacement["cost_per_sqft"],
            "subtotal": replacement["replacement_subtotal"],
            "contingency_percentage": replacement["contingency_percentage"],
            "contingency_cost": replacement["contingency_cost"],
            "total_project_cost": replacement["total_project_cost"],
            "component_costs": replacement["component_costs"],
            "confidence_score": replacement["confidence_score"],
        },
        "overlay": {
            "cost_per_sqft": replacement["overlay_cost_per_sqft"],
            "subtotal": replacement["overlay_subtotal"],
            "contingency_percentage": replacement["overlay_contingency_percentage"],
            "contingency_cost": replacement["overlay_contingency_cost"],
            "total_project_cost": replacement["overlay_total_project_cost"],
        },
        "coating": coating,
        "formula_source": {
            "score_minimum": COST_ESTIMATION_CONFIG.score_minimum,
            "score_maximum": COST_ESTIMATION_CONFIG.score_maximum,
        },
    }


def create_initial_snapshot(
    *,
    report_id: str,
    property_data: Mapping[str, Any],
    report_fields: Mapping[str, Any],
    analysis: Mapping[str, Any],
    imagery: Mapping[str, Any],
    created_by: str | None = None,
    persistent_square_footage_override: bool = False,
    generated_at: str | None = None,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Create Revision 1 from entirely fresh report inputs."""
    roof_area = report_fields.get("roof_area_sqft")
    condition_score = analysis.get("overall_score")
    calculations = calculate_report_values(roof_area, condition_score)
    created_at = generated_at or _utc_now()
    initial_analysis = deepcopy(dict(analysis))
    initial_analysis["summary"] = build_consistent_summary(
        initial_analysis,
        formatted_capture_date(imagery.get("capture_date")),
    )
    initial_analysis["recommendation"] = finalize_narrative(
        initial_analysis.get("recommendation"),
        REPORT_SUMMARY_CONFIG.recommendation_max_characters,
        REPORT_SUMMARY_CONFIG.fallback_recommendation,
    )
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": snapshot_id or str(uuid.uuid4()),
        "report_id": _nonempty_text(report_id, "report_id"),
        "revision": {
            "number": 1,
            "kind": "initial",
            "parent_snapshot_id": None,
            "created_at": created_at,
            "created_by": created_by,
            "change_reason": "Fresh assessment",
            "manual_edits": {},
        },
        "property": deepcopy(dict(property_data)),
        "report_fields": deepcopy(dict(report_fields)),
        "analysis": initial_analysis,
        "imagery": deepcopy(dict(imagery)),
        "calculations": calculations,
        "provenance": {
            "source_refreshed_at": created_at,
            "manual_fields": [],
            "persistent_square_footage_override": bool(persistent_square_footage_override),
        },
    }
    _synchronize_derived_fields(snapshot)
    validate_snapshot(snapshot)
    return snapshot


def create_manual_revision(
    parent_snapshot: Mapping[str, Any],
    edits: Mapping[str, Any],
    *,
    created_by: str,
    change_reason: str,
    apply_square_footage_to_future: bool = False,
    recommendation_refresher: Callable[[Mapping[str, Any]], str] | None = None,
    created_at: str | None = None,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Copy a completed snapshot, overlay allowed edits, and recalculate it."""
    validate_snapshot(parent_snapshot)
    unexpected = sorted(set(edits) - EDITABLE_FIELDS)
    if unexpected:
        raise SnapshotValidationError(f"Unsupported editable fields: {', '.join(unexpected)}")
    if not edits:
        raise SnapshotValidationError("At least one report field must be edited")
    if apply_square_footage_to_future and "roof_area_sqft" not in edits:
        raise SnapshotValidationError(
            "A future square-footage override requires a roof_area_sqft edit"
        )

    revised = deepcopy(dict(parent_snapshot))
    timestamp = created_at or _utc_now()
    revised["snapshot_id"] = snapshot_id or str(uuid.uuid4())
    revised["revision"] = {
        "number": int(parent_snapshot["revision"]["number"]) + 1,
        "kind": "manual_edit",
        "parent_snapshot_id": parent_snapshot["snapshot_id"],
        "created_at": timestamp,
        "created_by": _nonempty_text(created_by, "created_by"),
        "change_reason": _nonempty_text(change_reason, "change_reason"),
        "manual_edits": deepcopy(dict(edits)),
    }

    report_fields = revised["report_fields"]
    analysis = revised["analysis"]
    field_targets = {
        "roof_area_sqft": (report_fields, "roof_area_sqft"),
        "roof_type": (analysis, "roof_type"),
        "roof_system": (analysis, "roof_system"),
        "roof_condition_score": (analysis, "overall_score"),
        "report_summary": (analysis, "summary"),
        "recommendation": (analysis, "recommendation"),
    }
    for field, value in edits.items():
        target, target_field = field_targets[field]
        target[target_field] = value

    # Correct malformed inherited AI narratives without changing text that the
    # user explicitly edited for this revision.
    if "report_summary" not in edits:
        analysis["summary"] = finalize_narrative(
            analysis.get("summary"),
            REPORT_SUMMARY_CONFIG.summary_max_characters,
            REPORT_SUMMARY_CONFIG.fallback_summary,
        )
    if "recommendation" not in edits:
        analysis["recommendation"] = finalize_narrative(
            analysis.get("recommendation"),
            REPORT_SUMMARY_CONFIG.recommendation_max_characters,
            REPORT_SUMMARY_CONFIG.fallback_recommendation,
        )

    revised["calculations"] = calculate_report_values(
        report_fields.get("roof_area_sqft"),
        analysis.get("overall_score"),
    )
    _synchronize_derived_fields(revised)
    if {"roof_type", "roof_condition_score"}.intersection(edits) and "report_summary" not in edits:
        analysis["summary"] = build_consistent_summary(
            analysis,
            formatted_capture_date(revised["imagery"].get("capture_date")),
        )

    recommendation_dependencies = {"roof_type", "roof_system", "roof_condition_score"}
    if recommendation_dependencies.intersection(edits) and "recommendation" not in edits:
        if recommendation_refresher is None:
            raise SnapshotValidationError(
                "Roof information or condition edits require a refreshed or manually edited recommendation"
            )
        analysis["recommendation"] = _nonempty_text(
            recommendation_refresher(revised),
            "recommendation_refresher result",
        )

    revised["provenance"]["manual_fields"] = sorted(edits)
    revised["provenance"]["persistent_square_footage_override"] = bool(
        apply_square_footage_to_future
    )
    validate_snapshot(revised)
    return revised


def _synchronize_derived_fields(snapshot: dict[str, Any]) -> None:
    calculations = snapshot["calculations"]
    snapshot["report_fields"]["roof_area_sqft"] = calculations["roof_area_sqft"]
    snapshot["report_fields"]["roof_squares"] = calculations["roof_squares"]
    snapshot["analysis"]["overall_score"] = calculations["roof_condition_score"]
    snapshot["analysis"]["condition_label"] = calculations["condition_label"]
    snapshot["analysis"]["risk_level"] = calculations["risk_level"]


def validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    """Validate core invariants without adding a runtime JSON Schema dependency."""
    if not isinstance(snapshot, Mapping):
        raise SnapshotValidationError("Snapshot must be an object")
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise SnapshotValidationError("Unsupported snapshot schema_version")
    for field in ("snapshot_id", "report_id"):
        _nonempty_text(snapshot.get(field), field)
    for section in (
        "revision",
        "property",
        "report_fields",
        "analysis",
        "imagery",
        "calculations",
        "provenance",
    ):
        if not isinstance(snapshot.get(section), Mapping):
            raise SnapshotValidationError(f"{section} must be an object")

    revision = snapshot["revision"]
    try:
        revision_number = int(revision.get("number"))
    except (TypeError, ValueError) as exc:
        raise SnapshotValidationError("revision.number must be a positive integer") from exc
    if revision_number < 1 or revision_number != revision.get("number"):
        raise SnapshotValidationError("revision.number must be a positive integer")
    if revision.get("kind") not in {"initial", "manual_edit"}:
        raise SnapshotValidationError("revision.kind is unsupported")
    if revision_number == 1 and revision.get("parent_snapshot_id") is not None:
        raise SnapshotValidationError("Initial snapshots cannot have a parent")
    if revision_number > 1 and not revision.get("parent_snapshot_id"):
        raise SnapshotValidationError("Manual revisions require a parent snapshot")
    if not isinstance(revision.get("manual_edits"), Mapping):
        raise SnapshotValidationError("revision.manual_edits must be an object")

    property_data = snapshot["property"]
    _nonempty_text(property_data.get("canonical_key"), "property.canonical_key")
    _nonempty_text(property_data.get("address"), "property.address")

    analysis = snapshot["analysis"]
    for field in ("roof_type", "roof_system", "summary", "recommendation"):
        if not isinstance(analysis.get(field), str):
            raise SnapshotValidationError(f"analysis.{field} must be text")

    imagery = snapshot["imagery"]
    if not isinstance(imagery.get("source"), str):
        raise SnapshotValidationError("imagery.source must be text")
    if not isinstance(imagery.get("limitations"), list):
        raise SnapshotValidationError("imagery.limitations must be an array")

    calculations = snapshot["calculations"]
    expected = calculate_report_values(
        snapshot["report_fields"].get("roof_area_sqft"),
        snapshot["analysis"].get("overall_score"),
    )
    for field in (
        "roof_area_sqft",
        "roof_squares",
        "roof_condition_score",
        "condition_label",
        "risk_level",
        "replacement",
        "overlay",
        "coating",
    ):
        if calculations.get(field) != expected[field]:
            raise SnapshotValidationError(f"calculations.{field} is inconsistent")


def snapshot_to_renderer_inputs(
    snapshot: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Translate a validated snapshot into the existing PDF renderer inputs."""
    validate_snapshot(snapshot)
    row = deepcopy(dict(snapshot["report_fields"]))
    property_data = snapshot["property"]
    imagery = snapshot["imagery"]
    aliases = {
        "Address": property_data.get("address"),
        "Building City": property_data.get("city"),
        "Building State": property_data.get("state"),
        "Building ZIP": property_data.get("zip_code"),
        "County": property_data.get("county"),
        "Parcel Number": property_data.get("parcel_number"),
        "Building Footprint Sq Ft": row.get("roof_area_sqft"),
        "Primary Aerial Source": imagery.get("source"),
        "Primary Aerial Photo Date": imagery.get("capture_date"),
    }
    for field, value in aliases.items():
        if value is not None:
            row[field] = value
    analysis = deepcopy(dict(snapshot["analysis"]))
    manual_fields = snapshot["provenance"].get("manual_fields") or []
    if "roof_type" in manual_fields:
        # A manually confirmed roofing-surface statement is authoritative for
        # this revision and must not be replaced by inherited AI zones.
        analysis["_manual_roof_type_display"] = analysis.get("roof_type")
    if "roof_system" in manual_fields:
        # A manually confirmed physical configuration is authoritative for
        # this revision.
        analysis["_manual_roof_system_display"] = analysis.get("roof_system")
    return row, analysis


__all__ = [
    "CALCULATION_VERSION",
    "EDITABLE_FIELDS",
    "SNAPSHOT_SCHEMA_PATH",
    "SNAPSHOT_SCHEMA_VERSION",
    "SnapshotValidationError",
    "calculate_report_values",
    "condition_label_for_score",
    "create_initial_snapshot",
    "create_manual_revision",
    "refresh_recommendation",
    "risk_level_for_score",
    "snapshot_to_renderer_inputs",
    "validate_snapshot",
]
