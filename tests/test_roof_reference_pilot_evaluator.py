import json
import tempfile
import unittest
from pathlib import Path

from evaluate_roof_reference_pilot import evaluate_pilot


class RoofReferencePilotEvaluatorTests(unittest.TestCase):
    def _write_fixture(self, root: Path, roof_type: str, confidence: int, expected: str, maximum: int | None = None) -> Path:
        analysis = {
            "source": "openai",
            "ai_confidence": confidence,
            "building_classification": "single",
            "roof_type": roof_type,
            "roof_system": roof_type,
            "roof_zones": [
                {
                    "zone_id": "A",
                    "location": "main roof",
                    "roof_type": roof_type,
                    "estimated_area_percentage": 100,
                    "confidence": confidence,
                    "supporting_cues": ["fixture"],
                    "alternatives": [],
                    "limitations": [],
                }
            ],
            "reference_workflow": {"workflow_version": "test"},
        }
        (root / "analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
        maximum_line = f"\n    maximum_ai_confidence: {maximum}" if maximum is not None else ""
        expected_path = root / "expected.yaml"
        expected_path.write_text(
            "schema_version: 1\n"
            'workflow_version: "test"\n'
            "examples:\n"
            '  - parcel: "1"\n'
            "    address: Test Roof\n"
            "    analysis_json: analysis.json\n"
            f'    expected_roof_system: "{expected}"'
            f"{maximum_line}\n",
            encoding="utf-8",
        )
        return expected_path

    def test_matching_result_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = self._write_fixture(root, "metal", 55, "Primary: Metal", 60)
            result = evaluate_pilot(expected, root)[0]
        self.assertTrue(result.passed)

    def test_mismatch_and_confidence_cap_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = self._write_fixture(root, "tpo", 78, "Primary: Metal", 60)
            result = evaluate_pilot(expected, root)[0]
        self.assertFalse(result.passed)
        self.assertEqual(len(result.failures), 2)

    def test_pvc_is_normalized_to_combined_label(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = self._write_fixture(root, "pvc", 55, "Primary: PVC or Coated Roof")
            result = evaluate_pilot(expected, root)[0]
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
