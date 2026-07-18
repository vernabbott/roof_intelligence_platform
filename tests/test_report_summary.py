import tempfile
import unittest
from pathlib import Path

from generate_roof_intelligence_reports import (
    analysis_prompt,
    apply_visual_risk_adjustment,
    fallback_analysis,
)
from report_summary_config import (
    DEFAULT_REPORT_SUMMARY_PATH,
    REPORT_SUMMARY_CONFIG,
    ReportSummaryConfigurationError,
    load_report_summary_config,
)


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

    def test_ai_prompt_includes_markdown_guidance(self) -> None:
        prompt = analysis_prompt({"Address": "123 Test Street"})
        self.assertIn(REPORT_SUMMARY_CONFIG.ai_guidance, prompt)

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
            "summary": "Dark staining is visible.",
            "recommendation": REPORT_SUMMARY_CONFIG.fallback_recommendation,
            "observations": [],
            "breakdown": {},
            "visual_risk_factors": {"notes": []},
        }
        adjusted = apply_visual_risk_adjustment(analysis)
        expected_label = REPORT_SUMMARY_CONFIG.visual_risk_factors["dark_staining_or_discoloration"].label
        self.assertIn(expected_label, adjusted["summary"])


if __name__ == "__main__":
    unittest.main()
