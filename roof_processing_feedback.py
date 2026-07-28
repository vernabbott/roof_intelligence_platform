#!/usr/bin/env python3
"""Reviewed feedback records for improving future roof-report processing."""

from __future__ import annotations

from copy import deepcopy
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Mapping
import uuid


FEEDBACK_SCHEMA_VERSION = 1
REVIEW_STATUSES = frozenset({"pending_review", "approved", "rejected", "applied"})
FIELD_SCOPES = {
    "roof_area_sqft": "property_measurement",
    "roof_type": "material_reference",
    "roof_system": "roof_configuration",
    "roof_condition_score": "condition_scoring",
    "report_summary": "narrative_guidance",
    "recommendation": "recommendation_guidance",
}


class ProcessingFeedbackError(ValueError):
    """Raised when a future-processing feedback record is invalid."""


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _text(value: object, field: str) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        raise ProcessingFeedbackError(f"{field} must be non-empty text")
    return text


def _snapshot_field(snapshot: Mapping[str, Any], field: str) -> object:
    if field == "roof_area_sqft":
        return (snapshot.get("report_fields") or {}).get("roof_area_sqft")
    analysis = snapshot.get("analysis") or {}
    return {
        "roof_type": analysis.get("roof_type"),
        "roof_system": analysis.get("roof_system"),
        "roof_condition_score": analysis.get("overall_score"),
        "report_summary": analysis.get("summary"),
        "recommendation": analysis.get("recommendation"),
    }.get(field)


def validate_feedback_record(record: Mapping[str, Any]) -> None:
    if not isinstance(record, Mapping):
        raise ProcessingFeedbackError("feedback record must be an object")
    if record.get("schema_version") != FEEDBACK_SCHEMA_VERSION:
        raise ProcessingFeedbackError("unsupported feedback schema_version")
    for field in ("feedback_id", "report_id", "parent_snapshot_id", "revised_snapshot_id"):
        _text(record.get(field), field)
    if record.get("status") not in REVIEW_STATUSES:
        raise ProcessingFeedbackError("unsupported feedback status")
    if not isinstance(record.get("corrections"), Mapping) or not record["corrections"]:
        raise ProcessingFeedbackError("feedback corrections must be a non-empty object")
    unknown = sorted(set(record["corrections"]) - set(FIELD_SCOPES))
    if unknown:
        raise ProcessingFeedbackError(f"unsupported feedback fields: {', '.join(unknown)}")
    if not isinstance(record.get("learning_scopes"), list) or not record["learning_scopes"]:
        raise ProcessingFeedbackError("learning_scopes must be a non-empty list")
    _text(record.get("comment"), "comment")
    if not isinstance(record.get("property_identity"), Mapping):
        raise ProcessingFeedbackError("property_identity must be an object")
    _text(record["property_identity"].get("canonical_key"), "property_identity.canonical_key")
    if not isinstance(record.get("imagery_identity"), Mapping):
        raise ProcessingFeedbackError("imagery_identity must be an object")
    review = record.get("review")
    application = record.get("application")
    if record["status"] in {"approved", "rejected", "applied"}:
        if not isinstance(review, Mapping):
            raise ProcessingFeedbackError("review metadata is required after review")
        _text(review.get("reviewed_by"), "review.reviewed_by")
        _text(review.get("decision_note"), "review.decision_note")
    if record["status"] == "applied":
        if not isinstance(application, Mapping):
            raise ProcessingFeedbackError("application metadata is required for applied feedback")
        _text(application.get("workflow_version"), "application.workflow_version")
        _text(application.get("applied_by"), "application.applied_by")
        artifacts = application.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ProcessingFeedbackError("applied feedback must name at least one artifact")


def build_feedback_candidate(
    parent_snapshot: Mapping[str, Any],
    revised_snapshot: Mapping[str, Any],
    *,
    requested_by: str,
    feedback_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Create an opt-in feedback candidate without applying it to future reports."""
    revision = revised_snapshot.get("revision") or {}
    edits = revision.get("manual_edits")
    if not isinstance(edits, Mapping) or not edits:
        raise ProcessingFeedbackError("revised snapshot contains no manual edits")
    corrections = {
        field: {
            "before": deepcopy(_snapshot_field(parent_snapshot, field)),
            "after": deepcopy(value),
        }
        for field, value in edits.items()
    }
    property_data = parent_snapshot.get("property") or {}
    imagery = parent_snapshot.get("imagery") or {}
    analysis = parent_snapshot.get("analysis") or {}
    record = {
        "schema_version": FEEDBACK_SCHEMA_VERSION,
        "feedback_id": feedback_id or str(uuid.uuid4()),
        "status": "pending_review",
        "report_id": _text(revised_snapshot.get("report_id"), "report_id"),
        "parent_snapshot_id": _text(parent_snapshot.get("snapshot_id"), "parent_snapshot_id"),
        "revised_snapshot_id": _text(revised_snapshot.get("snapshot_id"), "revised_snapshot_id"),
        "requested_by": _text(requested_by, "requested_by"),
        "created_at": created_at or _utc_now(),
        "comment": _text(revision.get("change_reason"), "comment"),
        "corrections": corrections,
        "learning_scopes": sorted({FIELD_SCOPES[field] for field in edits}),
        "property_identity": {
            key: deepcopy(property_data.get(key))
            for key in (
                "property_id",
                "canonical_key",
                "address",
                "city",
                "state",
                "zip_code",
                "county",
                "parcel_number",
            )
        },
        "imagery_identity": {
            "source": imagery.get("source"),
            "capture_date": imagery.get("capture_date"),
            "report_image_asset_id": imagery.get("report_image_asset_id"),
            "reference_workflow": deepcopy(analysis.get("reference_workflow")),
        },
        "review": None,
        "application": None,
    }
    validate_feedback_record(record)
    return record


def review_feedback(
    record: Mapping[str, Any],
    *,
    approved: bool,
    reviewed_by: str,
    decision_note: str,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    """Approve or reject a pending candidate; approval still does not apply it."""
    validate_feedback_record(record)
    if record.get("status") != "pending_review":
        raise ProcessingFeedbackError("only pending feedback can be reviewed")
    reviewed = deepcopy(dict(record))
    reviewed["status"] = "approved" if approved else "rejected"
    reviewed["review"] = {
        "reviewed_by": _text(reviewed_by, "reviewed_by"),
        "decision_note": _text(decision_note, "decision_note"),
        "reviewed_at": reviewed_at or _utc_now(),
    }
    validate_feedback_record(reviewed)
    return reviewed


def mark_feedback_applied(
    record: Mapping[str, Any],
    *,
    workflow_version: str,
    artifacts: list[str] | tuple[str, ...],
    applied_by: str,
    applied_at: str | None = None,
) -> dict[str, Any]:
    """Mark approved feedback applied only after durable workflow artifacts exist."""
    validate_feedback_record(record)
    if record.get("status") != "approved":
        raise ProcessingFeedbackError("only approved feedback can be applied")
    normalized_artifacts = [_text(value, "artifact") for value in artifacts]
    if not normalized_artifacts:
        raise ProcessingFeedbackError("at least one applied artifact is required")
    applied = deepcopy(dict(record))
    applied["status"] = "applied"
    applied["application"] = {
        "workflow_version": _text(workflow_version, "workflow_version"),
        "artifacts": normalized_artifacts,
        "applied_by": _text(applied_by, "applied_by"),
        "applied_at": applied_at or _utc_now(),
    }
    validate_feedback_record(applied)
    return applied


def save_feedback_record(record: Mapping[str, Any], directory: str | Path) -> Path:
    """Atomically persist one record as a review-queue JSON document."""
    validate_feedback_record(record)
    target_directory = Path(directory).expanduser().resolve()
    target_directory.mkdir(parents=True, exist_ok=True)
    target = target_directory / f"{record['feedback_id']}.json"
    temporary = target.with_name(f".{target.name}.writing")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    return target


__all__ = [
    "FEEDBACK_SCHEMA_VERSION",
    "ProcessingFeedbackError",
    "build_feedback_candidate",
    "mark_feedback_applied",
    "review_feedback",
    "save_feedback_record",
    "validate_feedback_record",
]
