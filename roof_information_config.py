#!/usr/bin/env python3
"""Validated Roof Information card configuration loaded from Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_ROOF_INFORMATION_PATH = Path(__file__).resolve().parent / "docs/ai/roof_information.md"


class RoofInformationConfigurationError(ValueError):
    """Raised when the active Roof Information configuration is invalid."""


@dataclass(frozen=True)
class RoofInformationConfig:
    primary_prefix: str
    secondary_prefix: str
    maximum_secondary_types: int
    minimum_secondary_confidence: int
    show_possible_types_row: bool
    show_material_percentages: bool
    component_exclusions: tuple[str, ...]
    ai_guidance: str


def _mapping(value: Any, location: str) -> dict:
    if not isinstance(value, dict):
        raise RoofInformationConfigurationError(f"{location} must be a YAML mapping")
    return value


def _text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoofInformationConfigurationError(f"{location} must be non-empty text")
    return value.strip()


def _integer(value: Any, location: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise RoofInformationConfigurationError(f"{location} must be between {minimum} and {maximum}")
    return value


def _boolean(value: Any, location: str) -> bool:
    if not isinstance(value, bool):
        raise RoofInformationConfigurationError(f"{location} must be true or false")
    return value


def load_roof_information_config(path: str | Path = DEFAULT_ROOF_INFORMATION_PATH) -> RoofInformationConfig:
    config_path = Path(path)
    try:
        document = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RoofInformationConfigurationError(f"Unable to read Roof Information configuration: {config_path}") from exc

    front_matter = re.match(r"\A---\s*\r?\n(.*?)\r?\n---", document, flags=re.DOTALL)
    if not front_matter:
        raise RoofInformationConfigurationError(f"{config_path} is missing YAML front matter")
    try:
        status = _mapping(yaml.safe_load(front_matter.group(1)), f"{config_path} front matter").get("status")
    except yaml.YAMLError as exc:
        raise RoofInformationConfigurationError(f"Invalid YAML front matter in {config_path}: {exc}") from exc
    if str(status or "").strip().lower() != "active":
        raise RoofInformationConfigurationError(f"{config_path} must have status: active")

    block = re.search(r"```yaml[ \t]+roof_information[ \t]*\r?\n(.*?)\r?\n```", document, flags=re.DOTALL)
    if not block:
        raise RoofInformationConfigurationError(f"{config_path} is missing the labeled roof_information YAML block")
    try:
        config = _mapping(yaml.safe_load(block.group(1)), "roof_information")
    except yaml.YAMLError as exc:
        raise RoofInformationConfigurationError(f"Invalid roof_information YAML in {config_path}: {exc}") from exc
    if config.get("schema_version") != 1:
        raise RoofInformationConfigurationError("roof_information.schema_version must be 1")

    display = _mapping(config.get("display"), "roof_information.display")
    exclusions = config.get("component_exclusions")
    if not isinstance(exclusions, list) or not exclusions:
        raise RoofInformationConfigurationError("roof_information.component_exclusions must be a non-empty list")
    return RoofInformationConfig(
        primary_prefix=_text(display.get("primary_prefix"), "roof_information.display.primary_prefix"),
        secondary_prefix=_text(display.get("secondary_prefix"), "roof_information.display.secondary_prefix"),
        maximum_secondary_types=_integer(
            display.get("maximum_secondary_types"), "roof_information.display.maximum_secondary_types", 0, 6
        ),
        minimum_secondary_confidence=_integer(
            display.get("minimum_secondary_confidence"),
            "roof_information.display.minimum_secondary_confidence",
            0,
            100,
        ),
        show_possible_types_row=_boolean(
            display.get("show_possible_types_row"), "roof_information.display.show_possible_types_row"
        ),
        show_material_percentages=_boolean(
            display.get("show_material_percentages"), "roof_information.display.show_material_percentages"
        ),
        component_exclusions=tuple(
            _text(value, f"roof_information.component_exclusions[{index}]").lower()
            for index, value in enumerate(exclusions)
        ),
        ai_guidance=_text(config.get("ai_guidance"), "roof_information.ai_guidance"),
    )


ROOF_INFORMATION_CONFIG = load_roof_information_config()


ROOF_TYPE_LABELS = {
    "tpo": "TPO",
    "pvc": "PVC",
    "epdm": "EPDM",
    "ballasted": "Ballasted",
    "metal": "Metal",
    "mod_bit": "Modified Bitumen",
    "tar_and_gravel": "Tar and Gravel / BUR",
    "coating": "Coated Roof",
    "pvc_or_coating": "PVC or Coated Roof",
    "epdm_or_mod_bit": "EPDM or Modified Bitumen",
    "mod_bit_or_coating": "Modified Bitumen or Coated Roof",
    "mod_bit_or_tar_and_gravel": "Modified Bitumen or Tar and Gravel",
    "ballasted_or_tar_and_gravel": "Ballasted or Tar and Gravel",
    "unknown": "Unknown",
}


def roof_system_card_text(analysis: dict, config: RoofInformationConfig = ROOF_INFORMATION_CONFIG) -> str:
    """Return one nonnumeric primary/secondary roof-system statement."""
    zones = analysis.get("roof_zones")
    if isinstance(zones, list) and zones:
        candidates: list[tuple[int, int, str, str]] = []
        for zone in zones:
            if not isinstance(zone, dict):
                continue
            key = str(zone.get("roof_type") or "").strip()
            if key in {"pvc", "coating"}:
                key = "pvc_or_coating"
            if key not in ROOF_TYPE_LABELS or key == "unknown":
                continue
            location = str(zone.get("location") or "").strip().lower()
            if any(term in location for term in config.component_exclusions):
                continue
            try:
                area = int(zone.get("estimated_area_percentage") or 0)
            except (TypeError, ValueError):
                area = 0
            try:
                confidence = int(zone.get("confidence") or 0)
            except (TypeError, ValueError):
                confidence = 0
            candidates.append((area, confidence, key, location))

        if candidates:
            candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
            primary_key = candidates[0][2]
            secondary: list[str] = []
            for _, confidence, key, _ in candidates[1:]:
                if key == primary_key or confidence < config.minimum_secondary_confidence or key in secondary:
                    continue
                secondary.append(key)
                if len(secondary) >= config.maximum_secondary_types:
                    break
            result = f"{config.primary_prefix} {ROOF_TYPE_LABELS[primary_key]}"
            if secondary:
                result += f"; {config.secondary_prefix} " + ", ".join(ROOF_TYPE_LABELS[key] for key in secondary)
            return result

    primary = str(analysis.get("roof_system") or analysis.get("roof_type") or "Unknown").strip()
    if primary.lower().startswith("mixed roof types:"):
        primary = primary.split(":", 1)[1].split(",", 1)[0].strip()
    if primary.lower() in {"pvc", "coated roof", "coating"}:
        primary = "PVC or Coated Roof"
    result = f"{config.primary_prefix} {primary or 'Unknown'}"
    systems = analysis.get("possible_roof_systems") or []
    secondary_labels: list[str] = []
    for item in systems:
        if not isinstance(item, dict):
            continue
        label = str(item.get("system") or "").strip()
        if label.lower() in {"pvc", "coated roof", "coating"}:
            label = "PVC or Coated Roof"
        try:
            confidence = int(item.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0
        if not label or label.lower() in primary.lower() or confidence < config.minimum_secondary_confidence:
            continue
        if label not in secondary_labels:
            secondary_labels.append(label)
        if len(secondary_labels) >= config.maximum_secondary_types:
            break
    if secondary_labels:
        result += f"; {config.secondary_prefix} " + ", ".join(secondary_labels)
    return result
