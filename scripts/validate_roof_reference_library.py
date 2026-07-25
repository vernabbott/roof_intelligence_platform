#!/usr/bin/env python3
"""Validate positive roof-reference registration, descriptions, and coverage."""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from roof_reference_config import RoofReferenceConfigurationError, load_roof_reference_config


IMAGE_PATTERN = re.compile(r"!\[([^\]]+)\]\(([^)\s]+)(?:\s+['\"][^'\"]*['\"])?\)")
HEADING_PATTERN = re.compile(r"^#{2,6}\s+\S")
MINIMUM_DESCRIPTION_CHARACTERS = 80


def guide_example_errors(guide_path: Path) -> list[str]:
    lines = guide_path.read_text(encoding="utf-8").splitlines()
    errors: list[str] = []
    current_heading = ""

    for index, line in enumerate(lines):
        if HEADING_PATTERN.match(line):
            current_heading = line.lstrip("#").strip()

        match = IMAGE_PATTERN.search(line)
        if not match:
            continue

        alt_text, target = match.groups()
        if not current_heading:
            errors.append(f"{guide_path}: image {target} has no preceding example heading")
        if len(alt_text.strip()) < 10:
            errors.append(f"{guide_path}: image {target} needs descriptive alt text")

        description_lines: list[str] = []
        for following in lines[index + 1 :]:
            if HEADING_PATTERN.match(following) or IMAGE_PATTERN.search(following):
                break
            if following.strip():
                description_lines.append(following.strip())
        description = " ".join(description_lines)
        if len(description) < MINIMUM_DESCRIPTION_CHARACTERS:
            errors.append(
                f"{guide_path}: image {target} needs at least "
                f"{MINIMUM_DESCRIPTION_CHARACTERS} characters of visible-cue description"
            )

    return errors


def duplicate_content_errors(config) -> list[str]:
    seen: dict[str, tuple[str, Path]] = {}
    errors: list[str] = []
    for roof_type, item in config.roof_types.items():
        for image_path in item.reference_image_paths:
            digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
            previous = seen.get(digest)
            if previous:
                previous_type, previous_path = previous
                errors.append(
                    "duplicate positive image content: "
                    f"{previous_type}/{previous_path.name} and {roof_type}/{image_path.name}"
                )
            else:
                seen[digest] = (roof_type, image_path)
    return errors


def main() -> int:
    try:
        config = load_roof_reference_config()
    except RoofReferenceConfigurationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []
    for item in config.roof_types.values():
        errors.extend(guide_example_errors(item.guide_path))
    errors.extend(duplicate_content_errors(config))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    total = sum(len(item.reference_image_paths) for item in config.roof_types.values())
    print(f"Roof reference library valid: workflow {config.workflow_version}, {total} positive images")
    for roof_type, item in config.roof_types.items():
        print(f"  {roof_type}: {len(item.reference_image_paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
