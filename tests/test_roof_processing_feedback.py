import json
from pathlib import Path
import tempfile
import unittest

from roof_intelligence_revision_service import regenerate_revision
from roof_intelligence_snapshot import create_initial_snapshot, create_manual_revision, refresh_recommendation
from roof_processing_feedback import (
    ProcessingFeedbackError,
    build_feedback_candidate,
    mark_feedback_applied,
    review_feedback,
    save_feedback_record,
)


def initial_snapshot() -> dict:
    return create_initial_snapshot(
        report_id="report-feedback-1",
        snapshot_id="snapshot-feedback-1",
        generated_at="2026-07-26T12:00:00+00:00",
        created_by="reviewer-1",
        property_data={
            "property_id": "property-1",
            "canonical_key": "CO:Denver:parcel:123",
            "address": "40 S Vallejo St",
            "city": "Denver",
            "state": "CO",
            "parcel_number": "123",
        },
        report_fields={"roof_area_sqft": 10_000},
        analysis={
            "roof_type": "Primary: TPO",
            "roof_system": "Single low-slope roof section",
            "overall_score": 78,
            "summary": "Initial summary.",
            "recommendation": "Initial recommendation.",
            "observations": ["Light roof field."],
        },
        imagery={
            "source": "Synthetic aerial",
            "capture_date": "2026-07-01",
            "report_image_asset_id": "asset-1",
            "limitations": [],
        },
    )


class RoofProcessingFeedbackTests(unittest.TestCase):
    def test_candidate_preserves_before_after_comment_and_identity(self) -> None:
        parent = initial_snapshot()
        revised = create_manual_revision(
            parent,
            {"roof_type": "Primary: White Single-Ply or Coated Roof", "roof_condition_score": 62},
            created_by="reviewer-1",
            change_reason="Weathering obscures the exact white membrane type",
            recommendation_refresher=refresh_recommendation,
            snapshot_id="snapshot-feedback-2",
            created_at="2026-07-26T13:00:00+00:00",
        )

        feedback = build_feedback_candidate(
            parent,
            revised,
            requested_by="reviewer-1",
            feedback_id="feedback-1",
            created_at="2026-07-26T13:01:00+00:00",
        )

        self.assertEqual(feedback["status"], "pending_review")
        self.assertEqual(feedback["corrections"]["roof_type"]["before"], "Primary: TPO")
        self.assertEqual(
            feedback["corrections"]["roof_type"]["after"],
            "Primary: White Single-Ply or Coated Roof",
        )
        self.assertEqual(feedback["property_identity"]["parcel_number"], "123")
        self.assertEqual(feedback["imagery_identity"]["report_image_asset_id"], "asset-1")
        self.assertEqual(
            feedback["learning_scopes"],
            ["condition_scoring", "material_reference"],
        )

    def test_feedback_requires_review_then_named_artifacts_before_application(self) -> None:
        parent = initial_snapshot()
        revised = create_manual_revision(
            parent,
            {"roof_type": "Primary: EPDM"},
            created_by="reviewer-1",
            change_reason="Field inspection confirmed EPDM membrane",
            recommendation_refresher=refresh_recommendation,
        )
        pending = build_feedback_candidate(parent, revised, requested_by="reviewer-1")

        with self.assertRaisesRegex(ProcessingFeedbackError, "only approved"):
            mark_feedback_applied(
                pending,
                workflow_version="2.4",
                artifacts=["docs/ai/roof_reference_manifest.yaml"],
                applied_by="codex",
            )
        approved = review_feedback(
            pending,
            approved=True,
            reviewed_by="roof-reviewer",
            decision_note="The correction is supported by the field inspection.",
        )
        applied = mark_feedback_applied(
            approved,
            workflow_version="2.4",
            artifacts=[
                "docs/ai/roof_reference_manifest.yaml",
                "docs/ai/roof_reference_eval_cases.yaml",
            ],
            applied_by="codex",
        )

        self.assertEqual(applied["status"], "applied")
        self.assertEqual(applied["application"]["workflow_version"], "2.4")
        self.assertEqual(len(applied["application"]["artifacts"]), 2)

    def test_revision_service_persists_opted_in_feedback_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            result = regenerate_revision(
                initial_snapshot(),
                {"roof_type": "Primary: EPDM"},
                created_by="reviewer-1",
                change_reason="Field inspection confirmed EPDM membrane",
                output_path=directory / "revision.pdf",
                submit_for_future_processing=True,
                feedback_directory=directory / "feedback",
            )

            feedback_path = Path(result["processing_feedback_path"])
            self.assertTrue(feedback_path.is_file())
            stored = json.loads(feedback_path.read_text(encoding="utf-8"))
            self.assertEqual(stored["status"], "pending_review")
            self.assertEqual(stored["revised_snapshot_id"], result["snapshot"]["snapshot_id"])

    def test_atomic_record_save_uses_feedback_id(self) -> None:
        parent = initial_snapshot()
        revised = create_manual_revision(
            parent,
            {"report_summary": "Corrected customer-facing summary."},
            created_by="reviewer-1",
            change_reason="The original summary overstated the visible condition",
        )
        feedback = build_feedback_candidate(
            parent,
            revised,
            requested_by="reviewer-1",
            feedback_id="feedback-save-1",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = save_feedback_record(feedback, temporary_directory)
            self.assertEqual(path.name, "feedback-save-1.json")
            self.assertEqual(json.loads(path.read_text())["feedback_id"], "feedback-save-1")


if __name__ == "__main__":
    unittest.main()
