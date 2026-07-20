# © PilotPoint IQ Roof Intelligence All rights reserved
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from generate_roof_intelligence_reports import (
    build_gemini_reference_parts,
    build_openai_candidate_content,
    build_openai_reference_content,
    call_gemini_reference_analysis,
    call_openai_reference_analysis,
    encode_image_data_url,
    image_mime_type,
    load_or_create_analysis,
    normalize_reference_analysis,
    reference_analysis_schema,
    roof_candidate_schema,
)
from roof_reference_config import (
    DEFAULT_ROOF_REFERENCE_MANIFEST_PATH,
    ROOF_REFERENCE_FEATURE_ENV,
    RoofReferenceConfigurationError,
    load_reference_bundle,
    load_roof_reference_config,
    roof_reference_feature_enabled,
    roof_reference_trace,
    select_reference_types,
)


class RoofReferenceConfigurationTests(unittest.TestCase):
    def test_manifest_loads_all_approved_types_and_images(self) -> None:
        config = load_roof_reference_config()
        self.assertEqual(len(config.roof_types), 7)
        self.assertEqual(sum(len(item.reference_image_paths) for item in config.roof_types.values()), 33)
        for item in config.roof_types.values():
            self.assertTrue(item.guide_path.is_file())
            self.assertTrue(set(item.stage2_image_paths).issubset(set(item.reference_image_paths)))
            self.assertFalse(any("damage" in path.name for path in item.reference_image_paths))
        ballasted = config.roof_types["ballasted"]
        self.assertIn("ballasted_005.jpg", [path.name for path in ballasted.reference_image_paths])
        self.assertIn("ballasted_005.jpg", [path.name for path in ballasted.stage2_image_paths])

    def test_missing_manifest_file_is_rejected(self) -> None:
        document = DEFAULT_ROOF_REFERENCE_MANIFEST_PATH.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "roof_reference_manifest.yaml"
            path.write_text(document.replace("tpo_001.jpg", "missing_tpo.jpg", 1), encoding="utf-8")
            with self.assertRaisesRegex(RoofReferenceConfigurationError, "does not exist"):
                load_roof_reference_config(path)

    def test_feature_flag_accepts_cli_or_environment(self) -> None:
        with patch.dict(os.environ, {ROOF_REFERENCE_FEATURE_ENV: "0"}, clear=False):
            self.assertFalse(roof_reference_feature_enabled(False))
            self.assertTrue(roof_reference_feature_enabled(True))
        with patch.dict(os.environ, {ROOF_REFERENCE_FEATURE_ENV: "true"}, clear=False):
            self.assertTrue(roof_reference_feature_enabled(False))

    def test_candidate_selection_preserves_zones_and_adds_confusion_companion(self) -> None:
        config = load_roof_reference_config()
        stage1 = {
            "roof_zones": [
                {"candidates": [{"roof_type": "tpo", "confidence": 76}]},
                {"candidates": [{"roof_type": "metal", "confidence": 93}]},
            ]
        }
        selected = select_reference_types(stage1, config)
        self.assertIn("tpo", selected)
        self.assertNotIn("pvc", selected)
        self.assertIn("metal", selected)
        self.assertLessEqual(len(selected), config.maximum_candidate_types)

    def test_coating_candidate_adds_tpo_and_ballasted_comparisons(self) -> None:
        config = load_roof_reference_config()
        stage1 = {
            "roof_zones": [
                {
                    "candidates": [
                        {"roof_type": "coating", "confidence": 52},
                        {"roof_type": "mod_bit", "confidence": 28},
                    ]
                }
            ]
        }
        selected = select_reference_types(stage1, config)
        self.assertIn("tpo", selected)
        self.assertIn("ballasted", selected)
        self.assertIn("mod_bit", selected)

    def test_secondary_coating_candidate_adds_mod_bit_and_ballasted_without_metal(self) -> None:
        config = load_roof_reference_config()
        stage1 = {
            "roof_zones": [
                {
                    "candidates": [
                        {"roof_type": "tpo", "confidence": 58},
                        {"roof_type": "pvc", "confidence": 46},
                        {"roof_type": "coating", "confidence": 28},
                    ]
                }
            ]
        }
        selected = select_reference_types(stage1, config)
        self.assertIn("mod_bit", selected)
        self.assertIn("ballasted", selected)

    def test_pvc_reference_is_loaded_when_pvc_is_a_leading_candidate(self) -> None:
        config = load_roof_reference_config()
        stage1 = {"roof_zones": [{"candidates": [{"roof_type": "pvc", "confidence": 78}]}]}
        self.assertIn("pvc", select_reference_types(stage1, config))

    def test_gray_tpo_candidate_adds_modified_bitumen_comparison(self) -> None:
        config = load_roof_reference_config()
        stage1 = {
            "roof_zones": [
                {
                    "visual_evidence": {"color_family": "gray"},
                    "candidates": [{"roof_type": "tpo", "confidence": 58}],
                }
            ]
        }
        selected = select_reference_types(stage1, config)
        self.assertIn("tpo", selected)
        self.assertIn("mod_bit", selected)


class RoofReferenceRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_roof_reference_config()
        cls.target_path = cls.config.roof_types["tpo"].reference_image_paths[0]
        cls.stage1 = {
            "building_classification": "mixed",
            "roof_zones": [
                {
                    "zone_id": "A",
                    "location": "main roof",
                    "estimated_area_percentage": 70,
                    "visual_evidence": {
                        "color_family": "white",
                        "seam_pattern": "broad_sheet_seams",
                        "surface_texture": "smooth",
                        "perimeter_stone_transition": "not_applicable",
                        "ridge_pattern": "not_apparent",
                        "evidence_summary": "Smooth white field with broad sheet seams",
                    },
                    "candidates": [
                        {"roof_type": "tpo", "confidence": 70, "evidence": "white broad sheets"}
                    ],
                    "limitations": [],
                },
                {
                    "zone_id": "B",
                    "location": "entrance",
                    "estimated_area_percentage": 30,
                    "visual_evidence": {
                        "color_family": "metallic",
                        "seam_pattern": "no_visible_seams",
                        "surface_texture": "ribbed",
                        "perimeter_stone_transition": "not_applicable",
                        "ridge_pattern": "long_parallel_raised",
                        "evidence_summary": "Rigid field with long parallel raised ribs",
                    },
                    "candidates": [
                        {"roof_type": "metal", "confidence": 90, "evidence": "raised ribs"}
                    ],
                    "limitations": [],
                },
            ],
            "overall_limitations": [],
        }

    def test_schemas_require_zone_level_output(self) -> None:
        self.assertIn("roof_zones", roof_candidate_schema(self.config)["required"])
        candidate_zone = roof_candidate_schema(self.config)["properties"]["roof_zones"]["items"]
        self.assertIn("visual_evidence", candidate_zone["required"])
        self.assertEqual(
            set(candidate_zone["properties"]["visual_evidence"]["required"]),
            {
                "color_family",
                "seam_pattern",
                "surface_texture",
                "perimeter_stone_transition",
                "ridge_pattern",
                "evidence_summary",
            },
        )
        self.assertIn("roof_zones", reference_analysis_schema()["required"])
        zone_type = reference_analysis_schema()["properties"]["roof_zones"]["items"]["properties"]["roof_type"]
        self.assertEqual(
            zone_type["enum"],
            [
                "tpo", "pvc", "epdm", "ballasted", "metal", "mod_bit", "tar_and_gravel", "coating", "pvc_or_coating",
                "epdm_or_mod_bit", "mod_bit_or_coating", "mod_bit_or_tar_and_gravel",
                "ballasted_or_tar_and_gravel", "unknown",
            ],
        )

    def test_dark_mixed_roof_selection_includes_epdm_mod_bit_pair(self) -> None:
        stage1 = {
            "roof_zones": [
                {"candidates": [{"roof_type": "tpo"}, {"roof_type": "pvc"}, {"roof_type": "coating"}]},
                {"candidates": [{"roof_type": "metal"}, {"roof_type": "mod_bit"}, {"roof_type": "epdm"}]},
                {"candidates": [{"roof_type": "metal"}, {"roof_type": "mod_bit"}, {"roof_type": "coating"}]},
            ]
        }
        selected = select_reference_types(stage1, self.config)
        self.assertIn("epdm", selected)
        self.assertIn("mod_bit", selected)
        self.assertNotIn("pvc", selected)

    def test_webp_target_uses_correct_mime_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "target.webp"
            path.write_bytes(b"test-webp-payload")
            self.assertEqual(image_mime_type(path), "image/webp")
            self.assertTrue(encode_image_data_url(path).startswith("data:image/webp;base64,"))

    def test_stage1_openai_request_contains_guide_and_actual_target_image(self) -> None:
        content = build_openai_candidate_content({}, self.target_path, self.config)
        text = "\n".join(item.get("text", "") for item in content)
        images = [item for item in content if item.get("type") == "input_image"]
        self.assertIn("Central classification guide", text)
        self.assertIn("Required Ambiguity Rules", text)
        self.assertIn("cap that zone confidence and overall ai_confidence at 60", text)
        self.assertIn("first record the required visual_evidence fields", text)
        self.assertIn("Fundamental Material Priors", text)
        self.assertEqual(len(images), 1)
        self.assertTrue(images[0]["image_url"].startswith("data:image/jpeg;base64,"))

    def test_stage2_provider_requests_use_same_guides_and_image_count(self) -> None:
        bundle = load_reference_bundle(["tpo", "metal"], self.config, images_per_type=1)
        openai_content = build_openai_reference_content({}, self.target_path, self.stage1, bundle, self.config)
        gemini_parts = build_gemini_reference_parts({}, self.target_path, self.stage1, bundle, self.config)
        openai_images = [item for item in openai_content if item.get("type") == "input_image"]
        gemini_images = [item for item in gemini_parts if "inlineData" in item]
        self.assertEqual(len(openai_images), 3)
        self.assertTrue(all(item.get("detail") == "high" for item in openai_images))
        self.assertEqual(len(gemini_images), 3)
        openai_text = "\n".join(item.get("text", "") for item in openai_content)
        gemini_text = "\n".join(item.get("text", "") for item in gemini_parts)
        for label in ("TPO", "Metal"):
            self.assertIn(f"IDENTIFICATION GUIDE — {label}", openai_text)
            self.assertIn(f"IDENTIFICATION GUIDE — {label}", gemini_text)
        self.assertIn("Required Ambiguity Rules", openai_text)
        self.assertIn("Required Ambiguity Rules", gemini_text)
        self.assertNotIn("roof_damage.md", openai_text)
        self.assertNotIn("roof_damage.md", gemini_text)
        self.assertIn("Use tpo as the default", openai_text)
        self.assertIn("Use metal as the type without", openai_text)
        self.assertIn("favor EPDM over metal", openai_text)
        self.assertIn("use pvc_or_coating", openai_text)
        self.assertIn("Favor pvc_or_coating over TPO", openai_text)
        self.assertIn("tan matte weathered asphaltic field may be modified bitumen", openai_text)
        self.assertIn("use ballasted_or_tar_and_gravel", openai_text)
        self.assertIn("Fundamental Material Priors", openai_text)
        self.assertIn("cap the affected zone confidence and overall ai_confidence at 60", openai_text)

    def test_trace_records_manifest_guides_images_and_stage1(self) -> None:
        bundle = load_reference_bundle(["tpo"], self.config, images_per_type=1)
        trace = roof_reference_trace(self.config, bundle, self.stage1, "openai", "test-model")
        self.assertEqual(trace["status"], "completed")
        self.assertEqual(trace["selected_reference_types"], ["tpo"])
        self.assertEqual(len(trace["guides"]), 1)
        self.assertEqual(len(trace["reference_images"]), 1)
        self.assertEqual(trace["stage1"], self.stage1)
        self.assertEqual(len(trace["manifest"]["sha256"]), 64)

    def final_analysis(self) -> dict:
        return {
            "best_image_source": "Primary aerial imagery",
            "roof_type": "TPO",
            "roof_system": "TPO",
            "possible_roof_systems": [
                {"system": "TPO/PVC", "confidence": 70, "evidence": "broad white sheets"}
            ],
            "roof_age_estimate": "Unknown",
            "roof_pitch": "Low slope",
            "overall_score": 80,
            "condition_label": "GOOD",
            "risk_level": "LOW",
            "ai_confidence": 70,
            "visual_risk_factors": {
                "dark_staining_or_discoloration": False,
                "suspected_ponding": False,
                "high_penetration_density": False,
                "overhanging_trees_or_debris": False,
                "notes": [],
            },
            "observations": ["One", "Two", "Three"],
            "breakdown": {
                "Membrane Condition": 80,
                "Ponding": 80,
                "Flashing & Seals": 80,
                "Penetrations": 80,
                "Overall Maintenance": 80,
            },
            "summary": "Summary",
            "recommendation": "Recommendation",
            "building_classification": "single",
            "roof_zones": [
                {
                    "zone_id": "A",
                    "location": "main roof",
                    "roof_type": "tpo",
                    "estimated_area_percentage": 100,
                    "confidence": 70,
                    "supporting_cues": ["broad white sheets"],
                    "alternatives": ["pvc", "coating"],
                    "limitations": ["aerial imagery"],
                }
            ],
        }

    def test_reference_analysis_uses_canonical_metal_type_in_legacy_summary(self) -> None:
        analysis = self.final_analysis()
        analysis["roof_type"] = "standing-seam metal"
        analysis["roof_system"] = "standing-seam metal"
        analysis["roof_zones"][0]["roof_type"] = "metal"
        analysis["roof_zones"][0]["alternatives"] = []
        normalize_reference_analysis(analysis)
        self.assertEqual(analysis["roof_type"], "Metal")
        self.assertEqual(analysis["roof_system"], "Metal")

    def test_reference_analysis_preserves_controlled_epdm_mod_bit_ambiguity(self) -> None:
        analysis = self.final_analysis()
        analysis["roof_zones"][0]["roof_type"] = "epdm_or_mod_bit"
        analysis["roof_zones"][0]["alternatives"] = ["epdm", "mod_bit"]
        normalize_reference_analysis(analysis)
        self.assertEqual(analysis["roof_type"], "EPDM or Modified Bitumen")
        self.assertEqual(analysis["roof_system"], "EPDM or Modified Bitumen")

    def test_reference_analysis_combines_standalone_pvc_and_coating(self) -> None:
        for standalone_type in ("pvc", "coating"):
            with self.subTest(standalone_type=standalone_type):
                analysis = self.final_analysis()
                analysis["roof_zones"][0]["roof_type"] = standalone_type
                normalize_reference_analysis(analysis)
                self.assertEqual(analysis["roof_zones"][0]["roof_type"], "pvc_or_coating")
                self.assertEqual(analysis["roof_type"], "PVC or Coated Roof")
                self.assertEqual(analysis["roof_system"], "PVC or Coated Roof")

    def test_openai_two_stage_orchestration_records_combined_usage(self) -> None:
        stage1_response = {"usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}}
        stage2_response = {"usage": {"input_tokens": 300, "output_tokens": 50, "total_tokens": 350}}
        with patch(
            "generate_roof_intelligence_reports.call_openai_structured",
            side_effect=[(self.stage1, stage1_response), (self.final_analysis(), stage2_response)],
        ) as api_call:
            result = call_openai_reference_analysis({}, self.target_path, "test-model")
        self.assertEqual(api_call.call_count, 2)
        self.assertEqual(result["reference_workflow"]["status"], "completed")
        self.assertIn("tpo", result["reference_workflow"]["selected_reference_types"])
        self.assertNotIn("pvc", result["reference_workflow"]["selected_reference_types"])
        self.assertEqual(result["usage"]["total_tokens"], 470)

    def test_gemini_two_stage_orchestration_records_trace(self) -> None:
        stage1_response = {"usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 20, "totalTokenCount": 120}}
        stage2_response = {"usageMetadata": {"promptTokenCount": 300, "candidatesTokenCount": 50, "totalTokenCount": 350}}
        with patch(
            "generate_roof_intelligence_reports.call_gemini_structured",
            side_effect=[(self.stage1, stage1_response), (self.final_analysis(), stage2_response)],
        ) as api_call:
            result = call_gemini_reference_analysis({}, self.target_path, "test-model")
        self.assertEqual(api_call.call_count, 2)
        self.assertEqual(result["reference_workflow"]["provider"], "gemini")
        self.assertEqual(result["usage"]["total_tokens"], 470)


class RoofReferenceFallbackTests(unittest.TestCase):
    def test_feature_off_preserves_legacy_one_call_path(self) -> None:
        legacy = {"source": "openai", "roof_type": "Legacy result"}
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "generate_roof_intelligence_reports.call_openai_reference_analysis"
            ) as reference_call, patch(
                "generate_roof_intelligence_reports.call_openai_analysis",
                return_value=legacy.copy(),
            ) as legacy_call:
                analysis = load_or_create_analysis(
                    {},
                    Path("target.jpg"),
                    None,
                    Path(temp_dir),
                    True,
                    "openai",
                    "test-model",
                    False,
                    False,
                )
        reference_call.assert_not_called()
        legacy_call.assert_called_once()
        self.assertNotIn("reference_workflow", analysis)

    def test_feature_failure_retries_legacy_ai_before_static_fallback(self) -> None:
        legacy = {"source": "openai", "roof_type": "Legacy result"}
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "generate_roof_intelligence_reports.call_openai_reference_analysis",
                side_effect=RuntimeError("reference failure"),
            ), patch(
                "generate_roof_intelligence_reports.call_openai_analysis",
                return_value=legacy.copy(),
            ) as legacy_call:
                analysis = load_or_create_analysis(
                    {},
                    Path("target.jpg"),
                    None,
                    Path(temp_dir),
                    True,
                    "openai",
                    "test-model",
                    False,
                    True,
                )
        legacy_call.assert_called_once()
        self.assertEqual(analysis["source"], "openai")
        self.assertEqual(analysis["reference_workflow"]["status"], "legacy_fallback")


if __name__ == "__main__":
    unittest.main()
