import tempfile
import unittest
from pathlib import Path

from generate_roof_intelligence_reports import analysis_prompt
from roof_information_config import (
    DEFAULT_ROOF_INFORMATION_PATH,
    ROOF_INFORMATION_CONFIG,
    RoofInformationConfigurationError,
    load_roof_information_config,
    roof_structure_card_text,
    roof_system_card_text,
    roof_type_card_text,
)


class RoofInformationConfigurationTests(unittest.TestCase):
    def test_active_markdown_configuration_loads(self) -> None:
        self.assertEqual(load_roof_information_config(), ROOF_INFORMATION_CONFIG)
        self.assertFalse(ROOF_INFORMATION_CONFIG.show_possible_types_row)
        self.assertFalse(ROOF_INFORMATION_CONFIG.show_material_percentages)

    def test_draft_configuration_is_rejected(self) -> None:
        document = DEFAULT_ROOF_INFORMATION_PATH.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "roof_information.md"
            path.write_text(document.replace("status: active", "status: draft", 1), encoding="utf-8")
            with self.assertRaisesRegex(RoofInformationConfigurationError, "status: active"):
                load_roof_information_config(path)

    def test_prompt_includes_roof_information_guidance(self) -> None:
        self.assertIn(ROOF_INFORMATION_CONFIG.ai_guidance, analysis_prompt({}))

    def test_primary_only_omits_low_confidence_and_component_types(self) -> None:
        analysis = {
            "roof_zones": [
                {
                    "location": "dominant main roof field",
                    "roof_type": "ballasted",
                    "estimated_area_percentage": 70,
                    "confidence": 95,
                },
                {
                    "location": "smaller attached light-colored roof sections",
                    "roof_type": "tpo",
                    "estimated_area_percentage": 15,
                    "confidence": 44,
                },
                {
                    "location": "small rooftop caps/enclosures/penthouse-like appendages",
                    "roof_type": "metal",
                    "estimated_area_percentage": 15,
                    "confidence": 55,
                },
            ]
        }
        self.assertEqual(roof_system_card_text(analysis), "Primary: Ballasted")

    def test_supported_secondary_type_has_no_percentage(self) -> None:
        analysis = {
            "roof_zones": [
                {
                    "location": "main roof",
                    "roof_type": "metal",
                    "estimated_area_percentage": 80,
                    "confidence": 88,
                },
                {
                    "location": "east attached roof addition",
                    "roof_type": "tpo",
                    "estimated_area_percentage": 20,
                    "confidence": 63,
                },
            ]
        }
        result = roof_system_card_text(analysis)
        self.assertEqual(result, "Primary: Metal; Secondary: TPO")
        self.assertNotIn("%", result)

    def test_pvc_and_coating_are_combined_in_roof_information(self) -> None:
        for standalone_type in ("pvc", "coating", "pvc_or_coating"):
            with self.subTest(standalone_type=standalone_type):
                analysis = {
                    "roof_zones": [
                        {
                            "location": "main roof",
                            "roof_type": standalone_type,
                            "estimated_area_percentage": 100,
                            "confidence": 58,
                        }
                    ]
                }
                self.assertEqual(roof_system_card_text(analysis), "Primary: PVC or Coated Roof")

    def test_manual_display_override_takes_precedence_over_roof_zones(self) -> None:
        analysis = {
            "_manual_roof_type_display": "Primary: EPDM",
            "roof_zones": [
                {
                    "location": "main roof",
                    "roof_type": "mod_bit",
                    "estimated_area_percentage": 100,
                    "confidence": 95,
                }
            ],
        }

        self.assertEqual(
            roof_type_card_text(analysis),
            "Primary: EPDM",
        )

    def test_roof_system_describes_physical_configuration(self) -> None:
        analysis = {
            "roof_structure": {
                "sections": "multiple",
                "slopes": "multiple",
                "slope_form": "low_slope",
                "air_conditioning_units": "present",
                "solar_panels": "not_visible",
                "skylights": "present",
            }
        }

        self.assertEqual(
            roof_structure_card_text(analysis),
            "Multiple connected roof sections; Multiple low-slope planes; "
            "A/C units present; no solar panels visible; "
            "skylights present",
        )

    def test_legacy_parapet_assessment_is_not_displayed(self) -> None:
        analysis = {
            "roof_structure": {
                "sections": "single",
                "slopes": "single",
                "slope_form": "low_slope",
                "parapet_walls": "present",
                "air_conditioning_units": "not_visible",
                "solar_panels": "not_visible",
                "skylights": "not_visible",
            }
        }

        result = roof_structure_card_text(analysis)

        self.assertNotIn("parapet", result.lower())


if __name__ == "__main__":
    unittest.main()
