import tempfile
import unittest
from pathlib import Path

from generate_roof_intelligence_reports import (
    analysis_prompt,
    apply_visual_risk_adjustment,
    fallback_analysis,
    visible_concerns_text,
)
from report_summary_config import (
    DEFAULT_REPORT_SUMMARY_PATH,
    REPORT_SUMMARY_CONFIG,
    ReportSummaryConfigurationError,
    finalize_narrative,
    load_report_summary_config,
)
from roof_assessment import build_consistent_summary, canonical_observations


class ReportSummaryConfigurationTests(unittest.TestCase):
    def test_active_markdown_configuration_loads(self) -> None:
        config = load_report_summary_config()
        self.assertEqual(config, REPORT_SUMMARY_CONFIG)
        self.assertIn("silicone roof restoration", config.ai_guidance)
        self.assertIn("onsite inspection", config.contractor_addendum)

    def test_draft_configuration_is_rejected(self) -> None:
        document = DEFAULT_REPORT_SUMMARY_PATH.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report_summary.md"
            path.write_text(document.replace("status: active", "status: draft", 1), encoding="utf-8")
            with self.assertRaisesRegex(ReportSummaryConfigurationError, "status: active"):
                load_report_summary_config(path)

    def test_markdown_wording_change_drives_fallback_configuration(self) -> None:
        document = DEFAULT_REPORT_SUMMARY_PATH.read_text(encoding="utf-8")
        original = REPORT_SUMMARY_CONFIG.fallback_summary
        replacement = "A Markdown-configured fallback summary."
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report_summary.md"
            path.write_text(document.replace(original, replacement, 1), encoding="utf-8")
            config = load_report_summary_config(path)
            self.assertEqual(config.fallback_summary, replacement)

    def test_fallback_summary_and_recommendation_come_from_markdown(self) -> None:
        analysis = fallback_analysis({}, "Primary aerial imagery")
        self.assertEqual(analysis["summary"], REPORT_SUMMARY_CONFIG.fallback_summary)
        self.assertEqual(analysis["recommendation"], REPORT_SUMMARY_CONFIG.fallback_recommendation)

    def test_incomplete_summary_with_unexpected_character_ends_at_last_sentence(self) -> None:
        text = (
            "The main field has uneven color and mottling. "
            "Numerous penetrations increase flashing and leak-risk potential, and近"
        )

        finalized = finalize_narrative(text, 475, REPORT_SUMMARY_CONFIG.fallback_summary)

        self.assertEqual(
            finalized,
            (
                "The main field has uneven color and mottling. "
                "Numerous penetrations increase flashing and leak-risk potential."
            ),
        )
        self.assertNotIn("近", finalized)

    def test_single_incomplete_narrative_is_completed(self) -> None:
        finalized = finalize_narrative(
            "The roof appears serviceable but requires an onsite inspection",
            475,
            REPORT_SUMMARY_CONFIG.fallback_summary,
        )

        self.assertEqual(
            finalized,
            "The roof appears serviceable but requires an onsite inspection.",
        )

    def test_ai_prompt_includes_markdown_guidance(self) -> None:
        prompt = analysis_prompt({"Address": "123 Test Street"})
        self.assertIn(REPORT_SUMMARY_CONFIG.ai_guidance, prompt)
        self.assertIn("tree_proximity to confirmed only", prompt)
        self.assertIn("Do not infer trees from shadows", prompt)
        self.assertIn("Never mention AI, workflow stages, reviewer confirmation", prompt)

    def test_customer_narratives_exclude_reference_matching_process(self) -> None:
        analysis = {
            "roof_type": "Primary: Modified Bitumen",
            "roof_zones": [
                {
                    "roof_type": "mod_bit",
                    "location": "entire reviewer-confirmed target roof",
                    "estimated_area_percentage": 100,
                    "supporting_cues": [
                        "Reviewer-confirmed exact building match to aging_002.png.",
                        "Weathered asphaltic field with narrow roll-lap geometry.",
                    ],
                }
            ],
            "observations": [
                "The reference image matched the parcel and imagery source.",
                "Localized patching and surface wear are visible.",
            ],
            "overall_score": 58,
            "condition_label": "POOR",
            "risk_level": "HIGH",
            "visual_risk_factors": {
                "dark_staining_or_discoloration": True,
                "suspected_ponding": False,
                "high_penetration_density": False,
                "overhanging_trees_or_debris": False,
                "tree_proximity": "indeterminate",
            },
        }

        observations = canonical_observations(analysis)
        analysis["observations"] = observations
        summary = build_consistent_summary(analysis)
        customer_text = " ".join(observations + [summary]).lower()

        self.assertIn("modified bitumen", customer_text)
        self.assertIn("weathered asphaltic field", customer_text)
        self.assertIn("poor condition", summary.lower())
        for process_term in ("reference", "match", "reviewer", "parcel", "aging_002.png"):
            self.assertNotIn(process_term, customer_text)
        self.assertNotIn("Localized patching and surface wear are visible.", summary)

    def test_post_processing_adds_configured_contractor_direction(self) -> None:
        analysis = {
            "overall_score": 80,
            "summary": "The roof appears serviceable.",
            "recommendation": "Continue routine maintenance.",
            "observations": [],
            "breakdown": {},
            "visual_risk_factors": {
                "dark_staining_or_discoloration": False,
                "suspected_ponding": False,
                "high_penetration_density": False,
                "overhanging_trees_or_debris": False,
                "tree_proximity": "indeterminate",
                "notes": [],
            },
        }
        adjusted = apply_visual_risk_adjustment(analysis)
        self.assertIn("qualified commercial roof-coating contractor", adjusted["recommendation"])
        self.assertLessEqual(
            len(adjusted["recommendation"]),
            REPORT_SUMMARY_CONFIG.recommendation_max_characters,
        )

    def test_visual_risk_language_comes_from_markdown(self) -> None:
        analysis = {
            "overall_score": 80,
            "summary": "This provisional summary is not canonical.",
            "recommendation": REPORT_SUMMARY_CONFIG.fallback_recommendation,
            "observations": ["Dark staining is visible."],
            "breakdown": {},
            "visual_risk_factors": {"notes": []},
        }
        adjusted = apply_visual_risk_adjustment(analysis)
        expected_label = REPORT_SUMMARY_CONFIG.visual_risk_factors["dark_staining_or_discoloration"].label
        self.assertIn(expected_label, adjusted["summary"])

    def test_unconfirmed_tree_impact_is_removed_and_not_scored(self) -> None:
        analysis = {
            "roof_type": "Primary: EPDM",
            "overall_score": 80,
            "recommendation": REPORT_SUMMARY_CONFIG.fallback_recommendation,
            "observations": [
                "Possible tree shadows may indicate branches near the roof."
            ],
            "breakdown": {
                "Membrane Condition": 80,
                "Ponding": 80,
                "Flashing & Seals": 80,
                "Penetrations": 80,
                "Overall Maintenance": 80,
            },
            "visual_risk_factors": {
                "dark_staining_or_discoloration": False,
                "suspected_ponding": False,
                "high_penetration_density": False,
                "overhanging_trees_or_debris": True,
                "tree_proximity": "indeterminate",
                "notes": ["Possible tree-related debris exposure."],
            },
        }

        adjusted = apply_visual_risk_adjustment(analysis)

        self.assertFalse(adjusted["visual_risk_factors"]["overhanging_trees_or_debris"])
        self.assertEqual(adjusted["overall_score"], 80)
        self.assertNotIn("tree", " ".join(adjusted["observations"]).lower())
        self.assertNotIn("tree", adjusted["summary"].lower())
        self.assertNotIn("tree", visible_concerns_text(adjusted).lower())

    def test_debris_only_concern_does_not_claim_tree_impact(self) -> None:
        analysis = {
            "roof_type": "Primary: EPDM",
            "overall_score": 80,
            "recommendation": REPORT_SUMMARY_CONFIG.fallback_recommendation,
            "observations": ["Visible roof debris accumulation may restrict drainage."],
            "breakdown": {
                "Membrane Condition": 80,
                "Ponding": 80,
                "Flashing & Seals": 80,
                "Penetrations": 80,
                "Overall Maintenance": 80,
            },
            "visual_risk_factors": {
                "dark_staining_or_discoloration": False,
                "suspected_ponding": False,
                "high_penetration_density": False,
                "overhanging_trees_or_debris": True,
                "tree_proximity": "not_visible",
                "notes": ["Visible roof debris accumulation may restrict drainage."],
            },
        }

        adjusted = apply_visual_risk_adjustment(analysis)
        concerns = visible_concerns_text(adjusted)

        self.assertTrue(adjusted["visual_risk_factors"]["overhanging_trees_or_debris"])
        self.assertLessEqual(adjusted["overall_score"], 76)
        self.assertIn("roof debris exposure", concerns)
        self.assertNotIn("tree", concerns.lower())
        self.assertNotIn("tree", adjusted["summary"].lower())

    def test_confirmed_overhang_can_inform_observations_and_score(self) -> None:
        analysis = {
            "roof_type": "Primary: EPDM",
            "overall_score": 80,
            "recommendation": REPORT_SUMMARY_CONFIG.fallback_recommendation,
            "observations": [
                "Tree canopy and branches overhang the target roof edge."
            ],
            "breakdown": {
                "Membrane Condition": 80,
                "Ponding": 80,
                "Flashing & Seals": 80,
                "Penetrations": 80,
                "Overall Maintenance": 80,
            },
            "visual_risk_factors": {
                "dark_staining_or_discoloration": False,
                "suspected_ponding": False,
                "high_penetration_density": False,
                "overhanging_trees_or_debris": True,
                "tree_proximity": "confirmed",
                "notes": ["Tree canopy visibly overlaps the target roof edge."],
            },
        }

        adjusted = apply_visual_risk_adjustment(analysis)

        self.assertLessEqual(adjusted["overall_score"], 76)
        self.assertIn("tree canopy", " ".join(adjusted["observations"]).lower())
        self.assertIn("confirmed tree overhang", visible_concerns_text(adjusted))
        self.assertIn("tree", adjusted["summary"].lower())


if __name__ == "__main__":
    unittest.main()
