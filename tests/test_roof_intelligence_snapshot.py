import json
from pathlib import Path
import tempfile
import unittest

from render_roof_intelligence_snapshot import render_snapshot
from roof_intelligence_cutover_flags import (
    MASTER_FLAG,
    READ_FLAG,
    SHADOW_WRITE_FLAG,
    WORKER_FLAG,
    WRITE_FLAG,
    load_cutover_flags,
)
from roof_intelligence_snapshot import (
    SNAPSHOT_SCHEMA_PATH,
    SnapshotValidationError,
    calculate_report_values,
    create_initial_snapshot,
    create_manual_revision,
    snapshot_to_renderer_inputs,
    validate_snapshot,
)


def fresh_snapshot(*, area=10_000, score=75, summary="Fresh summary", recommendation="Fresh recommendation"):
    return create_initial_snapshot(
        report_id="report-1",
        snapshot_id="snapshot-1",
        generated_at="2026-07-22T12:00:00+00:00",
        created_by="user-1",
        property_data={
            "canonical_key": "CO:Denver:parcel:123",
            "address": "1 Test St, Denver, CO 80202",
            "parcel_number": "123",
        },
        report_fields={"roof_area_sqft": area, "year_built": 1998},
        analysis={
            "roof_type": "TPO",
            "roof_system": "Single-ply membrane",
            "overall_score": score,
            "summary": summary,
            "recommendation": recommendation,
            "observations": ["Synthetic fixture"],
        },
        imagery={"source": "Synthetic", "capture_date": None, "limitations": []},
    )


class RoofIntelligenceSnapshotTests(unittest.TestCase):
    def test_schema_file_is_valid_json_and_declares_v1(self):
        schema = json.loads(SNAPSHOT_SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)
        self.assertIn("calculations", schema["required"])
        self.assertIn("recommendation", schema["properties"]["analysis"]["required"])

    def test_calculations_use_area_and_condition_score(self):
        baseline = calculate_report_values(10_000, 75)
        larger = calculate_report_values(20_000, 75)
        lower_score = calculate_report_values(10_000, 50)

        self.assertEqual(baseline["roof_squares"], 100)
        self.assertEqual(larger["replacement"]["subtotal"], baseline["replacement"]["subtotal"] * 2)
        self.assertGreater(
            lower_score["replacement"]["cost_per_sqft"],
            baseline["replacement"]["cost_per_sqft"],
        )

    def test_manual_revision_preserves_parent_and_recalculates(self):
        original = fresh_snapshot()
        revised = create_manual_revision(
            original,
            {
                "roof_area_sqft": 20_000,
                "roof_condition_score": 50,
                "report_summary": "Manually corrected summary",
                "recommendation": "Manually corrected recommendation",
            },
            created_by="user-2",
            change_reason="Confirmed during onsite review",
            apply_square_footage_to_future=True,
            created_at="2026-07-23T12:00:00+00:00",
            snapshot_id="snapshot-2",
        )

        self.assertEqual(original["report_fields"]["roof_area_sqft"], 10_000)
        self.assertEqual(original["analysis"]["summary"], "Fresh summary")
        self.assertEqual(revised["revision"]["number"], 2)
        self.assertEqual(revised["revision"]["parent_snapshot_id"], "snapshot-1")
        self.assertEqual(revised["report_fields"]["roof_squares"], 200)
        self.assertEqual(revised["analysis"]["condition_label"], "POOR")
        self.assertEqual(revised["analysis"]["risk_level"], "HIGH")
        self.assertEqual(revised["analysis"]["summary"], "Manually corrected summary")
        self.assertEqual(revised["analysis"]["recommendation"], "Manually corrected recommendation")
        self.assertTrue(revised["provenance"]["persistent_square_footage_override"])
        validate_snapshot(revised)

    def test_future_override_requires_an_area_edit(self):
        with self.assertRaisesRegex(SnapshotValidationError, "requires a roof_area_sqft edit"):
            create_manual_revision(
                fresh_snapshot(),
                {"report_summary": "Edited"},
                created_by="user-1",
                change_reason="Narrative correction",
                apply_square_footage_to_future=True,
            )

    def test_condition_edit_requires_recommendation_alignment(self):
        with self.assertRaisesRegex(SnapshotValidationError, "require a refreshed"):
            create_manual_revision(
                fresh_snapshot(),
                {"roof_condition_score": 50},
                created_by="user-1",
                change_reason="Condition corrected",
            )

        revised = create_manual_revision(
            fresh_snapshot(),
            {"roof_condition_score": 50},
            created_by="user-1",
            change_reason="Condition corrected",
            recommendation_refresher=lambda snapshot: (
                "Updated recommendation for score "
                f"{snapshot['analysis']['overall_score']:g}"
            ),
        )
        self.assertEqual(revised["analysis"]["recommendation"], "Updated recommendation for score 50")

    def test_fresh_assessment_does_not_inherit_manual_narratives(self):
        edited = create_manual_revision(
            fresh_snapshot(),
            {"report_summary": "Old manual summary", "recommendation": "Old manual recommendation"},
            created_by="user-1",
            change_reason="Prior report edit",
        )
        refreshed = fresh_snapshot(
            summary="New AI summary",
            recommendation="New AI recommendation",
        )

        self.assertEqual(edited["analysis"]["summary"], "Old manual summary")
        self.assertEqual(refreshed["revision"]["number"], 1)
        self.assertEqual(refreshed["analysis"]["summary"], "New AI summary")
        self.assertEqual(refreshed["analysis"]["recommendation"], "New AI recommendation")
        self.assertEqual(refreshed["provenance"]["manual_fields"], [])

    def test_rejects_unknown_edit_fields(self):
        with self.assertRaisesRegex(SnapshotValidationError, "Unsupported editable fields"):
            create_manual_revision(
                fresh_snapshot(),
                {"parcel_number": "999"},
                created_by="user-1",
                change_reason="Not permitted",
            )

    def test_snapshot_translates_to_existing_renderer_inputs(self):
        snapshot = fresh_snapshot(area=12_345, score=65)
        row, analysis = snapshot_to_renderer_inputs(snapshot)

        self.assertEqual(row["Address"], "1 Test St, Denver, CO 80202")
        self.assertEqual(row["Parcel Number"], "123")
        self.assertEqual(row["Building Footprint Sq Ft"], 12_345)
        self.assertEqual(row["Primary Aerial Source"], "Synthetic")
        self.assertEqual(analysis["overall_score"], 65)

    def test_standalone_snapshot_renderer_creates_pdf_without_gis_or_ai(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "snapshot-report.pdf"
            render_snapshot(fresh_snapshot(), output_path)

            self.assertTrue(output_path.is_file())
            self.assertGreater(output_path.stat().st_size, 1_000)
            self.assertEqual(output_path.read_bytes()[:4], b"%PDF")


class RoofIntelligenceCutoverFlagTests(unittest.TestCase):
    def test_all_flags_default_to_local_workflow(self):
        flags = load_cutover_flags({})
        self.assertTrue(flags.local_workflow_active)
        self.assertFalse(flags.master_enabled)
        self.assertFalse(flags.reads_enabled)
        self.assertFalse(flags.writes_enabled)
        self.assertFalse(flags.worker_enabled)
        self.assertFalse(flags.shadow_writes_enabled)
        self.assertTrue(flags.local_reads_active)
        self.assertTrue(flags.local_writes_active)
        self.assertTrue(flags.local_worker_active)
        self.assertFalse(flags.fully_cut_over)

    def test_subordinate_flags_cannot_activate_without_master(self):
        flags = load_cutover_flags(
            {
                READ_FLAG: "1",
                WRITE_FLAG: "true",
                WORKER_FLAG: "yes",
                SHADOW_WRITE_FLAG: "on",
            }
        )
        self.assertTrue(flags.local_workflow_active)
        self.assertFalse(flags.reads_enabled)
        self.assertFalse(flags.writes_enabled)
        self.assertFalse(flags.worker_enabled)
        self.assertFalse(flags.shadow_writes_enabled)

    def test_master_allows_independent_staged_cutover(self):
        flags = load_cutover_flags(
            {MASTER_FLAG: "1", READ_FLAG: "1", WRITE_FLAG: "0", WORKER_FLAG: "0"}
        )
        self.assertTrue(flags.local_workflow_active)
        self.assertFalse(flags.local_reads_active)
        self.assertTrue(flags.local_writes_active)
        self.assertTrue(flags.local_worker_active)
        self.assertTrue(flags.reads_enabled)
        self.assertFalse(flags.writes_enabled)
        self.assertFalse(flags.worker_enabled)

    def test_shadow_writes_keep_local_writes_authoritative(self):
        flags = load_cutover_flags(
            {
                MASTER_FLAG: "1",
                WRITE_FLAG: "1",
                SHADOW_WRITE_FLAG: "1",
            }
        )
        self.assertTrue(flags.writes_enabled)
        self.assertTrue(flags.shadow_writes_enabled)
        self.assertTrue(flags.local_writes_active)
        self.assertFalse(flags.fully_cut_over)

    def test_full_cutover_requires_reads_writes_and_worker(self):
        flags = load_cutover_flags(
            {
                MASTER_FLAG: "1",
                READ_FLAG: "1",
                WRITE_FLAG: "1",
                WORKER_FLAG: "1",
            }
        )
        self.assertTrue(flags.fully_cut_over)
        self.assertFalse(flags.local_workflow_active)

    def test_current_pilotpoint_entry_points_do_not_import_cutover_modules(self):
        project_dir = Path(__file__).resolve().parents[1]
        for relative_path in (
            "generate_roof_intelligence_reports.py",
            "collect_county_buildings_with_parcels.py",
            "county_discovery_health.py",
        ):
            source = (project_dir / relative_path).read_text(encoding="utf-8")
            self.assertNotIn("roof_intelligence_cutover_flags", source)
            self.assertNotIn("roof_intelligence_snapshot", source)


if __name__ == "__main__":
    unittest.main()
