#!/usr/bin/env python3
"""Run the deterministic, offline roof-reference regression evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from roof_reference_config import load_roof_reference_config
from roof_reference_retrieval import find_known_building_match, rank_references


DEFAULT_CASES_PATH = PROJECT_ROOT / "docs/ai/roof_reference_eval_cases.yaml"


def _project_file(raw_path: object, location: str) -> Path:
    path = Path(str(raw_path or ""))
    if path.is_absolute():
        raise ValueError(f"{location} must be project-relative")
    resolved = (PROJECT_ROOT / path).resolve()
    try:
        resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"{location} escapes the project root") from exc
    if not resolved.is_file():
        raise ValueError(f"{location} does not exist: {path}")
    return resolved


def evaluate(cases_path: Path = DEFAULT_CASES_PATH) -> dict:
    document = yaml.safe_load(cases_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("roof reference evaluation cases must use schema_version: 1")
    cases = document.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("roof reference evaluation cases must contain a non-empty cases list")

    config = load_roof_reference_config()
    results: list[dict] = []
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    known_correct = 0
    top1_correct = 0
    top3_correct = 0
    classifications_correct = 0

    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"cases[{index}] must be a mapping")
        case_id = str(case.get("id") or f"case_{index + 1}")
        expected = str(case.get("expected_roof_type") or "")
        if expected not in config.roof_types:
            raise ValueError(f"{case_id}: unsupported expected_roof_type {expected!r}")
        target = _project_file(case.get("target_image"), f"{case_id}.target_image")
        property_row = case.get("property") or {}
        if not isinstance(property_row, dict):
            raise ValueError(f"{case_id}.property must be a mapping")

        known_match = find_known_building_match(property_row, config)
        _, ranked = rank_references(list(config.roof_types), config, target)
        predicted = known_match.roof_type if known_match else (ranked[0].roof_type if ranked else "unknown")
        expected_known = bool(case.get("expected_known_match", False))
        known_ok = (known_match is not None) == expected_known
        if known_match and expected_known:
            known_ok = known_ok and known_match.roof_type == expected
        expected_reference = case.get("expected_top_reference")
        top_reference = (
            str(ranked[0].reference.path.resolve().relative_to(PROJECT_ROOT.resolve()))
            if ranked
            else None
        )
        top1_ok = bool(ranked) and ranked[0].roof_type == expected
        if expected_reference:
            top1_ok = top1_ok and top_reference == str(expected_reference)
        top3_ok = any(item.roof_type == expected for item in ranked[:3])
        classification_ok = predicted == expected

        known_correct += int(known_ok)
        top1_correct += int(top1_ok)
        top3_correct += int(top3_ok)
        classifications_correct += int(classification_ok)
        confusion[expected][predicted] += 1
        results.append(
            {
                "id": case_id,
                "expected_roof_type": expected,
                "predicted_roof_type": predicted,
                "classification_correct": classification_ok,
                "known_match_correct": known_ok,
                "known_match_reference": (
                    str(known_match.reference.path.resolve().relative_to(PROJECT_ROOT.resolve()))
                    if known_match
                    else None
                ),
                "top_reference": top_reference,
                "top_reference_similarity": ranked[0].similarity if ranked else None,
                "top1_retrieval_correct": top1_ok,
                "top3_contains_expected_type": top3_ok,
            }
        )

    total = len(results)
    return {
        "workflow_version": config.workflow_version,
        "total_cases": total,
        "classification_accuracy": classifications_correct / total,
        "known_match_accuracy": known_correct / total,
        "top1_retrieval_accuracy": top1_correct / total,
        "top3_type_recall": top3_correct / total,
        "confusion_matrix": {
            expected: dict(predictions) for expected, predictions in sorted(confusion.items())
        },
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    try:
        result = evaluate(args.cases)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    passed = all(
        item["classification_correct"]
        and item["known_match_correct"]
        and item["top1_retrieval_correct"]
        for item in result["cases"]
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
