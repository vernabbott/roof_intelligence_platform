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
    apply_visual_risk_adjustment,
    call_gemini_reference_analysis,
    call_openai_reference_analysis,
    encode_image_data_url,
    image_mime_type,
    load_or_create_analysis,
    maximum_retrieved_reference_images,
    normalize_reference_analysis,
    reference_images_per_type,
    reference_analysis_schema,
    roof_candidate_schema,
)
from scripts.evaluate_roof_reference_library import evaluate
from roof_assessment import canonical_observations
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
from roof_reference_retrieval import (
    NORMALIZED_IMAGE_SIZE,
    find_known_building_match,
    normalized_roof_image,
    rank_references,
    retrieve_reference_bundle,
)


class RoofReferenceConfigurationTests(unittest.TestCase):
    def test_manifest_loads_all_approved_types_and_images(self) -> None:
        config = load_roof_reference_config()
        self.assertEqual(len(config.roof_types), 7)
        self.assertEqual(sum(len(item.reference_image_paths) for item in config.roof_types.values()), 36)
        for item in config.roof_types.values():
            self.assertTrue(item.guide_path.is_file())
            self.assertFalse(any("damage" in path.name for path in item.reference_image_paths))
        ballasted = config.roof_types["ballasted"]
        self.assertIn("ballasted_005.jpg", [path.name for path in ballasted.reference_image_paths])
        metal = config.roof_types["metal"]
        self.assertIn("metal_007.png", [path.name for path in metal.reference_image_paths])
        mod_bit_bundle = load_reference_bundle(["mod_bit"], config)
        self.assertEqual(mod_bit_bundle[0].image_paths, config.roof_types["mod_bit"].reference_image_paths)
        self.assertIn("aging_002.png", [path.name for path in mod_bit_bundle[0].image_paths])

    def test_obsolete_stage2_subset_is_rejected(self) -> None:
        document = DEFAULT_ROOF_REFERENCE_MANIFEST_PATH.read_text(encoding="utf-8")
        document = document.replace(
            "    reference_images:\n",
            "    stage2_images:\n"
            "      - docs/ai/roof_reference_library/tpo/images/tpo_001.jpg\n"
            "    reference_images:\n",
            1,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manifest.yaml"
            path.write_text(document, encoding="utf-8")
            with self.assertRaisesRegex(RoofReferenceConfigurationError, "stage2_images is obsolete"):
                load_roof_reference_config(path)

    def test_guide_and_manifest_image_registration_must_match(self) -> None:
        document = DEFAULT_ROOF_REFERENCE_MANIFEST_PATH.read_text(encoding="utf-8")
        document = document.replace(
            "      - docs/ai/roof_reference_library/tpo/images/tpo_001.jpg\n",
            "",
            1,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manifest.yaml"
            path.write_text(document, encoding="utf-8")
            with self.assertRaisesRegex(RoofReferenceConfigurationError, "image registration mismatch"):
                load_roof_reference_config(path)

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

    def test_retrieval_limits_have_bounded_production_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(reference_images_per_type(), 2)
            self.assertEqual(maximum_retrieved_reference_images(), 8)
        with patch.dict(os.environ, {"ROOF_REFERENCE_IMAGES_PER_TYPE": "all"}, clear=True):
            self.assertEqual(reference_images_per_type(), 1000)
        with patch.dict(os.environ, {"ROOF_REFERENCE_IMAGES_PER_TYPE": "3"}, clear=True):
            self.assertEqual(reference_images_per_type(), 3)

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
        final_schema = reference_analysis_schema()
        self.assertIn("roof_zones", final_schema["required"])
        self.assertIn("roof_structure", final_schema["required"])
        self.assertEqual(
            set(final_schema["properties"]["roof_structure"]["properties"]),
            {
                "sections",
                "slopes",
                "slope_form",
                "air_conditioning_units",
                "solar_panels",
                "skylights",
            },
        )
        visual_risk = final_schema["properties"]["visual_risk_factors"]
        self.assertIn("tree_proximity", visual_risk["required"])
        self.assertEqual(
            visual_risk["properties"]["tree_proximity"]["enum"],
            ["confirmed", "not_visible", "indeterminate"],
        )
        zone_type = final_schema["properties"]["roof_zones"]["items"]["properties"]["roof_type"]
        self.assertEqual(
            zone_type["enum"],
            [
                "tpo", "tpo_pvc_or_coating", "pvc", "epdm", "ballasted", "metal", "mod_bit",
                "tar_and_gravel", "coating", "pvc_or_coating",
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
        self.assertIn("do not treat TPO as a conclusion merely because the surface is white", text)
        self.assertIn("Fundamental Material Priors", text)
        self.assertIn("Uniform gray pixels are outside the target building", text)
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
        self.assertIn("Use tpo_pvc_or_coating for an unresolved", openai_text)
        self.assertIn("Use metal as the type without", openai_text)
        self.assertIn("favor EPDM over metal", openai_text)
        self.assertIn("use pvc_or_coating", openai_text)
        self.assertIn("Favor pvc_or_coating over TPO", openai_text)
        self.assertIn("tan matte weathered asphaltic field may be modified bitumen", openai_text)
        self.assertIn("Compare the target against every supplied reference image", openai_text)
        self.assertIn("reviewer-confirmed same-building match", openai_text)
        self.assertIn("REVIEWER-CONFIRMED POSITIVE", openai_text)
        self.assertIn("use ballasted_or_tar_and_gravel", openai_text)
        self.assertIn("Fundamental Material Priors", openai_text)
        self.assertIn("cap the affected zone confidence and overall ai_confidence at 60", openai_text)
        self.assertIn("must be ignored completely", openai_text)

    def test_trace_records_manifest_guides_images_and_stage1(self) -> None:
        bundle = load_reference_bundle(["tpo"], self.config, images_per_type=1)
        trace = roof_reference_trace(self.config, bundle, self.stage1, "openai", "test-model")
        self.assertEqual(trace["status"], "completed")
        self.assertEqual(trace["selected_reference_types"], ["tpo"])
        self.assertEqual(len(trace["guides"]), 1)
        self.assertEqual(len(trace["reference_images"]), 1)
        self.assertEqual(
            trace["reference_image_coverage"],
            [{"roof_type": "tpo", "approved_count": 5, "used_count": 1, "complete": False}],
        )
        self.assertEqual(trace["stage1"], self.stage1)
        self.assertEqual(len(trace["manifest"]["sha256"]), 64)

    def test_known_building_requires_parcel_source_and_image_date(self) -> None:
        row = {
            "Parcel Number": "0533100022000",
            "Primary Aerial Source": "Esri World Imagery",
            "Primary Aerial Photo Date": "2025-09-06",
        }
        match = find_known_building_match(row, self.config)
        self.assertIsNotNone(match)
        self.assertEqual(match.roof_type, "mod_bit")
        self.assertEqual(match.reference.path.name, "aging_002.png")
        changed_date = dict(row, **{"Primary Aerial Photo Date": "2025-09-07"})
        self.assertIsNone(find_known_building_match(changed_date, self.config))

    def test_normalized_crop_and_top_reference_retrieval(self) -> None:
        target = Path(
            "aerial_images_single_address/world_imagery/"
            "0533100022000-world_imagery-ai-target.png"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            normalized = normalized_roof_image(target, cache_dir=cache_dir)
            from PIL import Image

            with Image.open(normalized) as image:
                self.assertEqual(image.size, (NORMALIZED_IMAGE_SIZE, NORMALIZED_IMAGE_SIZE))
            _, ranked = rank_references(
                list(self.config.roof_types),
                self.config,
                target,
                cache_dir=cache_dir,
            )
        self.assertEqual(ranked[0].roof_type, "mod_bit")
        self.assertEqual(ranked[0].reference.path.name, "aging_002.png")

    def test_retrieval_bundle_is_balanced_and_bounded(self) -> None:
        target = Path(
            "aerial_images_single_address/world_imagery/"
            "0533100022000-world_imagery-ai-target.png"
        )
        row = {
            "Parcel Number": "0533100022000",
            "Primary Aerial Source": "Esri World Imagery",
            "Primary Aerial Photo Date": "2025-09-06",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            _, bundle = retrieve_reference_bundle(
                list(self.config.roof_types),
                self.config,
                target,
                known_match=find_known_building_match(row, self.config),
                max_images=8,
                images_per_type=2,
                cache_dir=Path(temp_dir),
            )
        self.assertLessEqual(sum(len(item.image_paths) for item in bundle), 8)
        self.assertTrue(all(len(item.image_paths) <= 2 for item in bundle))
        sources = [path.name for item in bundle for path in item.source_image_paths]
        self.assertIn("aging_002.png", sources)

    def test_offline_reference_evaluation_guards_corrected_building(self) -> None:
        result = evaluate()
        self.assertEqual(result["total_cases"], 1)
        self.assertEqual(result["classification_accuracy"], 1.0)
        self.assertEqual(result["known_match_accuracy"], 1.0)
        self.assertEqual(result["top1_retrieval_accuracy"], 1.0)

    def final_analysis(self) -> dict:
        return {
            "best_image_source": "Primary aerial imagery",
            "roof_type": "TPO",
            "roof_system": "Single low-slope roof section; A/C units not visible",
            "roof_structure": {
                "sections": "single",
                "slopes": "single",
                "slope_form": "low_slope",
                "air_conditioning_units": "not_visible",
                "solar_panels": "not_visible",
                "skylights": "not_visible",
            },
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
                "tree_proximity": "indeterminate",
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

    def test_reference_analysis_uses_canonical_metal_type_for_roof_type(self) -> None:
        analysis = self.final_analysis()
        analysis["roof_type"] = "standing-seam metal"
        analysis["roof_zones"][0]["roof_type"] = "metal"
        analysis["roof_zones"][0]["alternatives"] = []
        normalize_reference_analysis(analysis)
        self.assertEqual(analysis["roof_type"], "Primary: Metal")
        self.assertIn("Single low-slope plane", analysis["roof_system"])
        self.assertNotIn("Metal", analysis["roof_system"])

    def test_canonical_observations_capitalize_every_sentence_start(self) -> None:
        observations = canonical_observations(
            {
                "observations": [
                    "lowercase opening sentence. another lowercase sentence.",
                    '"quoted sentence starts lowercase." (parenthetical sentence starts lowercase.)',
                ]
            }
        )

        self.assertEqual(
            observations,
            [
                "Lowercase opening sentence. Another lowercase sentence.",
                '"Quoted sentence starts lowercase." (Parenthetical sentence starts lowercase.)',
            ],
        )

    def test_reference_analysis_preserves_controlled_epdm_mod_bit_ambiguity(self) -> None:
        analysis = self.final_analysis()
        analysis["roof_zones"][0]["roof_type"] = "epdm_or_mod_bit"
        analysis["roof_zones"][0]["alternatives"] = ["epdm", "mod_bit"]
        normalize_reference_analysis(analysis)
        self.assertEqual(analysis["roof_type"], "Primary: EPDM or Modified Bitumen")
        self.assertNotIn("EPDM", analysis["roof_system"])

    def test_reference_analysis_combines_standalone_pvc_and_coating(self) -> None:
        for standalone_type in ("pvc", "coating"):
            with self.subTest(standalone_type=standalone_type):
                analysis = self.final_analysis()
                analysis["roof_zones"][0]["roof_type"] = standalone_type
                normalize_reference_analysis(analysis)
                self.assertEqual(analysis["roof_zones"][0]["roof_type"], "pvc_or_coating")
                self.assertEqual(analysis["roof_type"], "Primary: PVC or Coated Roof")
                self.assertNotIn("PVC", analysis["roof_system"])

    def test_unresolved_white_secondary_stays_consistent_across_sections_and_score(self) -> None:
        analysis = self.final_analysis()
        analysis["overall_score"] = 73
        analysis["breakdown"] = {
            "Membrane Condition": 52,
            "Ponding": 46,
            "Flashing & Seals": 48,
            "Penetrations": 44,
            "Overall Maintenance": 48,
        }
        analysis["visual_risk_factors"] = {
            "dark_staining_or_discoloration": True,
            "suspected_ponding": False,
            "high_penetration_density": True,
            "overhanging_trees_or_debris": False,
            "tree_proximity": "indeterminate",
            "notes": [
                "Visible discoloration and many penetrations increase serviceability and leak risk."
            ],
        }
        analysis["roof_zones"] = [
            {
                "zone_id": "1",
                "location": "Main roof field",
                "roof_type": "ballasted_or_tar_and_gravel",
                "estimated_area_percentage": 70,
                "confidence": 55,
                "supporting_cues": ["Tan aggregate-covered field"],
                "alternatives": ["ballasted", "tar_and_gravel"],
                "limitations": ["Stone embedment is not resolved"],
            },
            {
                "zone_id": "2",
                "location": "Smaller attached roof",
                "roof_type": "tpo",
                "estimated_area_percentage": 30,
                "confidence": 58,
                "supporting_cues": ["Smooth bright-white surface"],
                "alternatives": ["pvc", "coating"],
                "limitations": ["Seams are not resolved and the materials cannot be separated"],
            },
        ]

        normalize_reference_analysis(analysis)
        synchronized = apply_visual_risk_adjustment(
            analysis,
            {"Primary Aerial Photo Date": "20240301"},
        )

        expected_type = (
            "Primary: Ballasted or Tar and Gravel; "
            "Secondary: White Single-Ply or Coated Roof"
        )
        self.assertEqual(synchronized["roof_type"], expected_type)
        self.assertEqual(
            synchronized["roof_zones"][1]["roof_type"],
            "tpo_pvc_or_coating",
        )
        self.assertTrue(
            any("White Single-Ply or Coated Roof" in item for item in synchronized["observations"])
        )
        self.assertIn("Ballasted or Tar and Gravel", synchronized["summary"])
        self.assertIn("White Single-Ply or Coated Roof", synchronized["summary"])
        self.assertIn(
            f"{synchronized['overall_score']}/100",
            synchronized["summary"],
        )
        self.assertEqual(synchronized["overall_score"], 48)

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

    def test_openai_known_building_skips_material_inference_and_locks_type(self) -> None:
        row = {
            "Parcel Number": "0533100022000",
            "Primary Aerial Source": "Esri World Imagery",
            "Primary Aerial Photo Date": "2025-09-06",
        }
        target = Path(
            "aerial_images_single_address/world_imagery/"
            "0533100022000-world_imagery-ai-target.png"
        )
        stage2_response = {
            "usage": {"input_tokens": 300, "output_tokens": 50, "total_tokens": 350}
        }
        with patch(
            "generate_roof_intelligence_reports.call_openai_structured",
            return_value=(self.final_analysis(), stage2_response),
        ) as api_call:
            result = call_openai_reference_analysis(row, target, "test-model")
        self.assertEqual(api_call.call_count, 1)
        self.assertEqual(result["roof_zones"][0]["roof_type"], "mod_bit")
        self.assertEqual(result["roof_zones"][0]["confidence"], 100)
        self.assertTrue(result["reference_workflow"]["known_building_match"]["matched"])
        self.assertEqual(result["usage"]["total_tokens"], 350)
        customer_text = " ".join(result["observations"]).lower()
        for process_term in ("reference", "match", "reviewer", "aging_002.png"):
            self.assertNotIn(process_term, customer_text)
        self.assertIn("modified bitumen", customer_text)

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
                    {
                        "Primary Aerial Target Mask Version": "canonical-footprint-v1",
                        "Primary Aerial Target Mask Coverage": "0.500000",
                    },
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
        self.assertEqual(
            analysis["target_scope"],
            {
                "policy": "selected canonical building footprint only",
                "mask_version": "canonical-footprint-v1",
                "mask_coverage": "0.500000",
            },
        )

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
