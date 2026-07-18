import tempfile
import unittest
from pathlib import Path

from roof_replacement_cost_estimator import (
    COST_ESTIMATION_CONFIG,
    DEFAULT_COST_ESTIMATION_PATH,
    CostConfidenceInputs,
    CostConfigurationError,
    confidence_score,
    cost_estimation_disclaimer,
    cost_per_sqft_for_condition,
    estimate_roof_coating_cost,
    estimate_roof_replacement_cost,
    load_cost_estimation_config,
    overlay_cost_per_sqft_for_condition,
)


class CostEstimationConfigurationTests(unittest.TestCase):
    def test_active_markdown_configuration_loads(self) -> None:
        config = load_cost_estimation_config()
        self.assertEqual(config, COST_ESTIMATION_CONFIG)
        self.assertEqual(
            [
                (option.years, option.minimum_cost_per_sqft, option.maximum_cost_per_sqft)
                for option in config.coating_warranty_options
            ],
            [(10, 3.50, 4.00), (15, 4.50, 5.00), (20, 5.50, 6.00)],
        )

    def test_draft_configuration_is_rejected(self) -> None:
        document = DEFAULT_COST_ESTIMATION_PATH.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cost_estimation.md"
            path.write_text(document.replace("status: active", "status: draft", 1), encoding="utf-8")
            with self.assertRaisesRegex(CostConfigurationError, "status: active"):
                load_cost_estimation_config(path)

    def test_report_disclaimer_is_loaded_from_markdown(self) -> None:
        disclaimer = cost_estimation_disclaimer()
        self.assertTrue(disclaimer.startswith("Cost estimates are derived"))
        self.assertTrue(disclaimer.endswith("an on-site inspection."))

    def test_markdown_rate_change_drives_calculation(self) -> None:
        document = DEFAULT_COST_ESTIMATION_PATH.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cost_estimation.md"
            path.write_text(document.replace("cost_per_sqft: 21.00", "cost_per_sqft: 20.00", 1), encoding="utf-8")
            config = load_cost_estimation_config(path)
            estimate = estimate_roof_replacement_cost(100, 1_000, config=config)
            self.assertEqual(estimate.cost_per_sqft, 20.00)
            self.assertEqual(estimate.total_project_cost, 23_000.00)


class CostEstimationParityTests(unittest.TestCase):
    def test_replacement_rate_boundaries_match_previous_calculations(self) -> None:
        cases = (
            (100, 21.00),
            (90, 21.00),
            (89.999, 21.50),
            (80, 21.50),
            (75, 22.00),
            (70, 22.75),
            (65, 23.50),
            (60, 24.50),
            (55, 25.50),
            (50, 26.75),
            (45, 28.00),
            (40.001, 28.50),
            (40, 29.00),
            (0, 29.00),
            (-1, 29.00),
        )
        for score, expected_rate in cases:
            with self.subTest(score=score):
                self.assertEqual(cost_per_sqft_for_condition(score), expected_rate)

    def test_overlay_rate_boundaries_match_previous_calculations(self) -> None:
        cases = (
            (100, 9.00),
            (76, 9.00),
            (75.999, 9.25),
            (71, 9.25),
            (66, 9.50),
            (61, 9.75),
            (56, 10.00),
            (51, 10.25),
            (46, 10.50),
            (40, 11.00),
            (39.999, 12.00),
            (0, 12.00),
            (-1, 12.00),
        )
        for score, expected_rate in cases:
            with self.subTest(score=score):
                self.assertEqual(overlay_cost_per_sqft_for_condition(score), expected_rate)

    def test_replacement_and_overlay_totals_preserve_calculation_order(self) -> None:
        estimate = estimate_roof_replacement_cost(roof_condition_score=76, roof_area_sqft=18_611)
        self.assertEqual(estimate.replacement_subtotal, 409_442.00)
        self.assertEqual(estimate.contingency_cost, 61_416.30)
        self.assertEqual(estimate.total_project_cost, 470_858.30)
        self.assertEqual(estimate.overlay_subtotal, 167_499.00)
        self.assertEqual(estimate.overlay_contingency_cost, 16_749.90)
        self.assertEqual(estimate.overlay_total_project_cost, 184_248.90)

    def test_coating_estimate_uses_yaml_warranty_ranges(self) -> None:
        estimate = estimate_roof_coating_cost(18_611)
        self.assertEqual(
            [
                (
                    option.years,
                    option.minimum_total_cost,
                    option.maximum_total_cost,
                )
                for option in estimate.warranty_options
            ],
            [
                (10, 65_138.50, 74_444.00),
                (15, 83_749.50, 93_055.00),
                (20, 102_360.50, 111_666.00),
            ],
        )

    def test_confidence_weights_preserve_previous_behavior(self) -> None:
        self.assertEqual(confidence_score(), 70)
        self.assertEqual(confidence_score(CostConfidenceInputs(image_resolution_poor=True)), 60)
        all_positive = CostConfidenceInputs(
            roof_type_confidently_identified=True,
            roof_area_accurately_measured=True,
            building_footprint_available=True,
            high_resolution_imagery_available=True,
        )
        self.assertEqual(confidence_score(all_positive), 100)
        all_negative = CostConfidenceInputs(
            shadows_obscure_roof=True,
            tree_coverage_obscures_roof=True,
            image_resolution_poor=True,
            roof_edges_hidden=True,
        )
        self.assertEqual(confidence_score(all_negative), 50)


if __name__ == "__main__":
    unittest.main()
