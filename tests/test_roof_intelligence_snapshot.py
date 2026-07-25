import json
from pathlib import Path
import tempfile
import unittest

from render_roof_intelligence_snapshot import render_snapshot
from roof_intelligence_cutover_flags import (
    EDITING_FLAG,
    MASTER_FLAG,
    READ_FLAG,
    SHADOW_WRITE_FLAG,
    WORKER_FLAG,
    WRITE_FLAG,
    load_cutover_flags,
)
from roof_intelligence_revision_service import regenerate_revision
from roof_information_config import roof_structure_card_text, roof_type_card_text
from roof_intelligence_snapshot import (
    SNAPSHOT_SCHEMA_PATH,
    SnapshotValidationError,
    calculate_report_values,
    create_initial_snapshot,
    create_manual_revision,
    refresh_recommendation,
    snapshot_to_renderer_inputs,
    validate_snapshot,
)


def fresh_snapshot(*, area=10_000, score=75, summary="Fresh summary.", recommendation="Fresh recommendation."):
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
            "roof_type": "Primary: TPO",
            "roof_system": "Single low-slope plane; A/C units present",
            "roof_structure": {
                "sections": "single",
                "slopes": "single",
                "slope_form": "low_slope",
                "air_conditioning_units": "present",
                "solar_panels": "not_visible",
                "skylights": "not_visible",
            },
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

    def test_persisted_snapshot_survives_json_round_trip(self):
        restored = json.loads(json.dumps(fresh_snapshot()))

        validate_snapshot(restored)
        revised = create_manual_revision(
            restored,
            {"roof_area_sqft": 12_500},
            created_by="user-2",
            change_reason="Confirmed during onsite review",
        )

        self.assertEqual(revised["revision"]["number"], 2)
        self.assertEqual(revised["calculations"]["roof_area_sqft"], 12_500)

    def test_manual_revision_preserves_parent_and_recalculates(self):
        original = fresh_snapshot()
        original_summary = original["analysis"]["summary"]
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
        self.assertEqual(original["analysis"]["summary"], original_summary)
        self.assertIn("Primary: TPO", original_summary)
        self.assertIn("75/100", original_summary)
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

    def test_default_recommendation_refresh_aligns_with_revised_facts(self):
        original = fresh_snapshot()
        revised = create_manual_revision(
            original,
            {
                "roof_type": "Primary: EPDM",
                "roof_system": "Single low-slope roof section; A/C units present",
                "roof_condition_score": 45,
            },
            created_by="user-1",
            change_reason="Field inspection confirmed assembly",
            recommendation_refresher=refresh_recommendation,
        )

        self.assertIn(
            "roof type EPDM and physical configuration "
            "Single low-slope roof section; A/C units present",
            revised["analysis"]["recommendation"],
        )
        self.assertIn("45/100 (poor)", revised["analysis"]["recommendation"])
        self.assertEqual(original["analysis"]["recommendation"], "Fresh recommendation.")

    def test_fresh_assessment_derives_summary_without_inheriting_manual_narratives(self):
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
        self.assertIn("Primary: TPO", refreshed["analysis"]["summary"])
        self.assertIn("75/100", refreshed["analysis"]["summary"])
        self.assertNotIn("Old manual summary", refreshed["analysis"]["summary"])
        self.assertNotIn("New AI summary", refreshed["analysis"]["summary"])
        self.assertEqual(refreshed["analysis"]["recommendation"], "New AI recommendation.")
        self.assertEqual(refreshed["provenance"]["manual_fields"], [])

    def test_revision_cleans_malformed_inherited_ai_summary(self):
        parent = fresh_snapshot()
        parent["analysis"]["summary"] = (
            "The main field has uneven color and mottling. "
            "Numerous penetrations increase leak-risk potential, and近"
        )
        revised = create_manual_revision(
            parent,
            {"roof_area_sqft": 12_500},
            created_by="user-1",
            change_reason="Field measurement corrected area",
        )

        self.assertEqual(
            revised["analysis"]["summary"],
            (
                "The main field has uneven color and mottling. "
                "Numerous penetrations increase leak-risk potential."
            ),
        )
        self.assertIn("近", parent["analysis"]["summary"])

    def test_manual_summary_edit_is_preserved_exactly(self):
        exact_summary = "Field-confirmed summary — preserve exactly"
        revised = create_manual_revision(
            fresh_snapshot(),
            {"report_summary": exact_summary},
            created_by="user-1",
            change_reason="Field inspection corrected narrative",
        )

        self.assertEqual(revised["analysis"]["summary"], exact_summary)

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

    def test_manual_roof_system_edit_controls_physical_configuration(self):
        original = fresh_snapshot()
        original["analysis"]["roof_zones"] = [
            {
                "location": "main roof",
                "roof_type": "mod_bit",
                "estimated_area_percentage": 70,
                "confidence": 90,
            },
            {
                "location": "attached section",
                "roof_type": "epdm_or_mod_bit",
                "estimated_area_percentage": 30,
                "confidence": 80,
            },
        ]
        revised = create_manual_revision(
            original,
            {"roof_system": "Multiple connected low-slope sections; A/C units present"},
            created_by="user-1",
            change_reason="Field inspection confirmed roof configuration",
            recommendation_refresher=refresh_recommendation,
        )

        _, analysis = snapshot_to_renderer_inputs(revised)

        self.assertEqual(
            roof_structure_card_text(analysis),
            "Multiple connected low-slope sections; A/C units present",
        )

    def test_manual_roof_type_edit_overrides_inherited_material_zones(self):
        original = fresh_snapshot()
        original["analysis"]["roof_zones"] = [
            {
                "location": "main roof",
                "roof_type": "tpo",
                "estimated_area_percentage": 100,
                "confidence": 90,
            }
        ]
        revised = create_manual_revision(
            original,
            {"roof_type": "Primary: EPDM"},
            created_by="user-1",
            change_reason="Field inspection confirmed roof material",
            recommendation_refresher=refresh_recommendation,
        )

        _, analysis = snapshot_to_renderer_inputs(revised)

        self.assertEqual(roof_type_card_text(analysis), "Primary: EPDM")

    def test_standalone_snapshot_renderer_creates_pdf_without_gis_or_ai(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "snapshot-report.pdf"
            render_snapshot(fresh_snapshot(), output_path)

            self.assertTrue(output_path.is_file())
            self.assertGreater(output_path.stat().st_size, 1_000)
            self.assertEqual(output_path.read_bytes()[:4], b"%PDF")

    def test_revision_service_recalculates_and_atomically_renders_pdf(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "revision-2.pdf"
            result = regenerate_revision(
                fresh_snapshot(),
                {"roof_area_sqft": 20_000, "roof_condition_score": 50},
                created_by="user-2",
                change_reason="Confirmed during onsite review",
                output_path=output_path,
                apply_square_footage_to_future=True,
            )

            self.assertEqual(result["snapshot"]["revision"]["number"], 2)
            self.assertEqual(result["snapshot"]["report_fields"]["roof_squares"], 200)
            self.assertEqual(result["snapshot"]["analysis"]["condition_label"], "POOR")
            self.assertTrue(output_path.is_file())
            self.assertEqual(output_path.read_bytes()[:4], b"%PDF")
            self.assertEqual(len(result["pdf_checksum"]), 64)


class RoofIntelligenceCutoverFlagTests(unittest.TestCase):
    def test_all_flags_default_to_local_workflow(self):
        flags = load_cutover_flags({})
        self.assertTrue(flags.local_workflow_active)
        self.assertFalse(flags.master_enabled)
        self.assertFalse(flags.reads_enabled)
        self.assertFalse(flags.writes_enabled)
        self.assertFalse(flags.worker_enabled)
        self.assertFalse(flags.shadow_writes_enabled)
        self.assertFalse(flags.editing_enabled)
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
                EDITING_FLAG: "on",
            }
        )
        self.assertTrue(flags.local_workflow_active)
        self.assertFalse(flags.reads_enabled)
        self.assertFalse(flags.writes_enabled)
        self.assertFalse(flags.worker_enabled)
        self.assertFalse(flags.shadow_writes_enabled)
        self.assertFalse(flags.editing_enabled)

    def test_editing_requires_master_and_editing_flags(self):
        self.assertFalse(load_cutover_flags({EDITING_FLAG: "1"}).editing_enabled)
        self.assertTrue(
            load_cutover_flags({MASTER_FLAG: "1", EDITING_FLAG: "1"}).editing_enabled
        )

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
