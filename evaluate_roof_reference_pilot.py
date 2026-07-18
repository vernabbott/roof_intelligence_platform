#!/usr/bin/env python3
"""Compare pilot roof-reference JSON results with reviewer-approved labels."""

from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from generate_roof_intelligence_reports import normalize_reference_analysis
from roof_information_config import roof_system_card_text


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_EXPECTED_PATH = PROJECT_ROOT / "docs/ai/roof_reference_pilot_expected.yaml"


class PilotEvaluationError(ValueError):
    """Raised when the pilot expectation file or an analysis record is invalid."""


@dataclass(frozen=True)
class PilotEvaluation:
    parcel: str
    address: str
    expected_roof_system: str
    actual_roof_system: str
    ai_confidence: int
    maximum_ai_confidence: int | None
    source: str
    workflow_version: str
    passed: bool
    failures: tuple[str, ...]


def _mapping(value: Any, location: str) -> dict:
    if not isinstance(value, dict):
        raise PilotEvaluationError(f"{location} must be a YAML mapping")
    return value


def _text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PilotEvaluationError(f"{location} must be non-empty text")
    return value.strip()


def _project_file(value: Any, location: str, project_root: Path) -> Path:
    relative = Path(_text(value, location))
    if relative.is_absolute():
        raise PilotEvaluationError(f"{location} must be relative to the project root")
    root = project_root.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PilotEvaluationError(f"{location} escapes the project root") from exc
    if not path.is_file():
        raise PilotEvaluationError(f"{location} does not exist: {relative}")
    return path


def load_pilot_expectations(path: Path = DEFAULT_EXPECTED_PATH) -> dict:
    try:
        data = _mapping(yaml.safe_load(path.read_text(encoding="utf-8")), "pilot expectations")
    except OSError as exc:
        raise PilotEvaluationError(f"Unable to read pilot expectations: {path}") from exc
    except yaml.YAMLError as exc:
        raise PilotEvaluationError(f"Invalid pilot expectations YAML: {exc}") from exc
    if data.get("schema_version") != 1:
        raise PilotEvaluationError("pilot expectations schema_version must be 1")
    _text(data.get("workflow_version"), "workflow_version")
    examples = data.get("examples")
    if not isinstance(examples, list) or not examples:
        raise PilotEvaluationError("examples must be a non-empty YAML list")
    return data


def evaluate_pilot(
    expectations_path: Path = DEFAULT_EXPECTED_PATH,
    project_root: Path = PROJECT_ROOT,
) -> list[PilotEvaluation]:
    data = load_pilot_expectations(expectations_path)
    results: list[PilotEvaluation] = []
    for index, raw_example in enumerate(data["examples"]):
        example = _mapping(raw_example, f"examples[{index}]")
        parcel = _text(example.get("parcel"), f"examples[{index}].parcel")
        address = _text(example.get("address"), f"examples[{index}].address")
        expected = _text(example.get("expected_roof_system"), f"examples[{index}].expected_roof_system")
        analysis_path = _project_file(example.get("analysis_json"), f"examples[{index}].analysis_json", project_root)
        try:
            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PilotEvaluationError(f"Unable to read analysis JSON for {parcel}: {analysis_path}") from exc
        if not isinstance(analysis, dict):
            raise PilotEvaluationError(f"Analysis JSON for {parcel} must contain an object")

        normalized = copy.deepcopy(analysis)
        if normalized.get("roof_zones"):
            normalize_reference_analysis(normalized)
        actual = roof_system_card_text(normalized)
        try:
            confidence = int(normalized.get("ai_confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0
        maximum = example.get("maximum_ai_confidence")
        if maximum is not None and (not isinstance(maximum, int) or isinstance(maximum, bool)):
            raise PilotEvaluationError(f"examples[{index}].maximum_ai_confidence must be an integer")

        failures: list[str] = []
        if actual != expected:
            failures.append(f"roof system: expected {expected!r}, got {actual!r}")
        if maximum is not None and confidence > maximum:
            failures.append(f"AI confidence: expected <= {maximum}, got {confidence}")
        workflow = normalized.get("reference_workflow") or {}
        results.append(
            PilotEvaluation(
                parcel=parcel,
                address=address,
                expected_roof_system=expected,
                actual_roof_system=actual,
                ai_confidence=confidence,
                maximum_ai_confidence=maximum,
                source=str(normalized.get("source") or ""),
                workflow_version=str(workflow.get("workflow_version") or ""),
                passed=not failures,
                failures=tuple(failures),
            )
        )
    return results


def print_results(results: list[PilotEvaluation]) -> None:
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        confidence = f"; confidence {result.ai_confidence}%" if result.maximum_ai_confidence is not None else ""
        print(
            f"{status} {result.parcel} {result.address}: {result.actual_roof_system}"
            f"{confidence}; workflow {result.workflow_version or 'unknown'}"
        )
        for failure in result.failures:
            print(f"  - {failure}")
    passed = sum(result.passed for result in results)
    print(f"\n{passed}/{len(results)} pilot examples passed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", type=Path, default=DEFAULT_EXPECTED_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = evaluate_pilot(args.expected)
    print_results(results)
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
