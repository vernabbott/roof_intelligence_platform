#!/usr/bin/env python3
"""Validated roof repair cost calculations driven by the cost-estimation Markdown configuration."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_COST_ESTIMATION_PATH = Path(__file__).resolve().parent / "docs/ai/cost_estimation.md"


class CostConfigurationError(ValueError):
    """Raised when the active cost-estimation configuration is missing or invalid."""


@dataclass(frozen=True)
class CostConfidenceInputs:
    roof_type_confidently_identified: bool = False
    roof_area_accurately_measured: bool = False
    building_footprint_available: bool = False
    high_resolution_imagery_available: bool = False
    shadows_obscure_roof: bool = False
    tree_coverage_obscures_roof: bool = False
    image_resolution_poor: bool = False
    roof_edges_hidden: bool = False


@dataclass(frozen=True)
class RateTier:
    minimum_score: float
    minimum_inclusive: bool
    cost_per_sqft: float


@dataclass(frozen=True)
class CoatingWarrantyRate:
    years: int
    minimum_cost_per_sqft: float
    maximum_cost_per_sqft: float


@dataclass(frozen=True)
class CostEstimationConfig:
    score_minimum: float
    score_maximum: float
    replacement_tiers: tuple[RateTier, ...]
    replacement_contingency_percentage: float
    replacement_components: dict[str, float]
    overlay_tiers: tuple[RateTier, ...]
    overlay_contingency_percentage: float
    coating_warranty_options: tuple[CoatingWarrantyRate, ...]
    confidence_base_score: float
    confidence_minimum_score: float
    confidence_maximum_score: float
    confidence_adjustments: dict[str, float]
    report_disclaimer: str


@dataclass(frozen=True)
class RoofReplacementEstimate:
    roof_condition_score: float
    roof_area_sqft: float
    cost_per_sqft: float
    overlay_cost_per_sqft: float
    replacement_subtotal: float
    overlay_subtotal: float
    overlay_contingency_cost: float
    overlay_total_project_cost: float
    component_costs: dict[str, float]
    contingency_percentage: float
    overlay_contingency_percentage: float
    contingency_cost: float
    total_project_cost: float
    confidence_score: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CoatingWarrantyEstimate:
    years: int
    minimum_cost_per_sqft: float
    maximum_cost_per_sqft: float
    minimum_total_cost: float
    maximum_total_cost: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RoofCoatingEstimate:
    roof_area_sqft: float
    warranty_options: tuple[CoatingWarrantyEstimate, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _mapping(value: Any, location: str) -> dict:
    if not isinstance(value, dict):
        raise CostConfigurationError(f"{location} must be a YAML mapping")
    return value


def _number(value: Any, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CostConfigurationError(f"{location} must be numeric")
    return float(value)


def _integer(value: Any, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CostConfigurationError(f"{location} must be an integer")
    return value


def _percentage(value: Any, location: str) -> float:
    percentage = _number(value, location)
    if not 0 <= percentage <= 1:
        raise CostConfigurationError(f"{location} must be between 0 and 1")
    return percentage


def _rate_tiers(
    value: Any,
    location: str,
    score_minimum: float,
    score_maximum: float,
) -> tuple[RateTier, ...]:
    if not isinstance(value, list) or not value:
        raise CostConfigurationError(f"{location} must be a non-empty YAML list")

    tiers: list[RateTier] = []
    for index, raw_tier in enumerate(value):
        tier = _mapping(raw_tier, f"{location}[{index}]")
        minimum_score = _number(tier.get("minimum_score"), f"{location}[{index}].minimum_score")
        minimum_inclusive = tier.get("minimum_inclusive")
        if not isinstance(minimum_inclusive, bool):
            raise CostConfigurationError(f"{location}[{index}].minimum_inclusive must be true or false")
        cost_per_sqft = _number(tier.get("cost_per_sqft"), f"{location}[{index}].cost_per_sqft")
        if not score_minimum <= minimum_score <= score_maximum:
            raise CostConfigurationError(f"{location}[{index}].minimum_score is outside the configured score range")
        if cost_per_sqft <= 0:
            raise CostConfigurationError(f"{location}[{index}].cost_per_sqft must be greater than zero")
        tiers.append(RateTier(minimum_score, minimum_inclusive, cost_per_sqft))

    thresholds = [tier.minimum_score for tier in tiers]
    if thresholds != sorted(thresholds, reverse=True) or len(thresholds) != len(set(thresholds)):
        raise CostConfigurationError(f"{location} minimum scores must be unique and ordered from highest to lowest")
    if tiers[-1].minimum_score != score_minimum or not tiers[-1].minimum_inclusive:
        raise CostConfigurationError(f"{location} must end with an inclusive tier at the minimum score")
    return tuple(tiers)


def _active_front_matter(document: str, path: Path) -> None:
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---", document, flags=re.DOTALL)
    if not match:
        raise CostConfigurationError(f"{path} is missing YAML front matter")
    front_matter = _mapping(yaml.safe_load(match.group(1)), f"{path} front matter")
    if str(front_matter.get("status", "")).strip().lower() != "active":
        raise CostConfigurationError(f"{path} must have status: active before it can drive runtime pricing")


def load_cost_estimation_config(path: str | Path = DEFAULT_COST_ESTIMATION_PATH) -> CostEstimationConfig:
    config_path = Path(path)
    try:
        document = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CostConfigurationError(f"Unable to read cost configuration: {config_path}") from exc

    _active_front_matter(document, config_path)
    match = re.search(
        r"```yaml[ \t]+cost_estimation[ \t]*\r?\n(.*?)\r?\n```",
        document,
        flags=re.DOTALL,
    )
    if not match:
        raise CostConfigurationError(f"{config_path} is missing the labeled cost_estimation YAML block")
    try:
        raw_config = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise CostConfigurationError(f"Invalid YAML in {config_path}: {exc}") from exc

    config = _mapping(raw_config, "cost_estimation")
    if config.get("schema_version") != 1:
        raise CostConfigurationError("cost_estimation.schema_version must be 1")

    score_range = _mapping(config.get("score_range"), "cost_estimation.score_range")
    score_minimum = _number(score_range.get("minimum"), "cost_estimation.score_range.minimum")
    score_maximum = _number(score_range.get("maximum"), "cost_estimation.score_range.maximum")
    if score_minimum >= score_maximum:
        raise CostConfigurationError("cost_estimation.score_range minimum must be less than maximum")

    replacement = _mapping(config.get("replacement"), "cost_estimation.replacement")
    replacement_tiers = _rate_tiers(
        replacement.get("pricing_tiers"),
        "cost_estimation.replacement.pricing_tiers",
        score_minimum,
        score_maximum,
    )
    replacement_contingency = _percentage(
        replacement.get("contingency_percentage"),
        "cost_estimation.replacement.contingency_percentage",
    )
    raw_components = _mapping(replacement.get("components"), "cost_estimation.replacement.components")
    replacement_components: dict[str, float] = {}
    for key, raw_component in raw_components.items():
        component = _mapping(raw_component, f"cost_estimation.replacement.components.{key}")
        label = str(component.get("label", "")).strip()
        if not label:
            raise CostConfigurationError(f"cost_estimation.replacement.components.{key}.label is required")
        replacement_components[label] = _percentage(
            component.get("percentage"),
            f"cost_estimation.replacement.components.{key}.percentage",
        )
    if abs(sum(replacement_components.values()) - 1.0) > 1e-9:
        raise CostConfigurationError("cost_estimation replacement component percentages must total 1.0")

    overlay = _mapping(config.get("overlay"), "cost_estimation.overlay")
    overlay_tiers = _rate_tiers(
        overlay.get("pricing_tiers"),
        "cost_estimation.overlay.pricing_tiers",
        score_minimum,
        score_maximum,
    )
    overlay_contingency = _percentage(
        overlay.get("contingency_percentage"),
        "cost_estimation.overlay.contingency_percentage",
    )

    coating = _mapping(config.get("coating"), "cost_estimation.coating")
    raw_warranty_options = coating.get("warranty_options")
    if not isinstance(raw_warranty_options, list) or len(raw_warranty_options) != 3:
        raise CostConfigurationError(
            "cost_estimation.coating.warranty_options must contain exactly three options for the report layout"
        )
    coating_warranty_options: list[CoatingWarrantyRate] = []
    for index, raw_option in enumerate(raw_warranty_options):
        location = f"cost_estimation.coating.warranty_options[{index}]"
        option = _mapping(raw_option, location)
        years = _integer(option.get("years"), f"{location}.years")
        minimum_rate = _number(option.get("minimum_cost_per_sqft"), f"{location}.minimum_cost_per_sqft")
        maximum_rate = _number(option.get("maximum_cost_per_sqft"), f"{location}.maximum_cost_per_sqft")
        if years <= 0:
            raise CostConfigurationError(f"{location}.years must be greater than zero")
        if minimum_rate < 0 or maximum_rate < minimum_rate:
            raise CostConfigurationError(f"{location} rates must be non-negative and ordered minimum to maximum")
        coating_warranty_options.append(CoatingWarrantyRate(years, minimum_rate, maximum_rate))
    warranty_years = [option.years for option in coating_warranty_options]
    if warranty_years != sorted(warranty_years) or len(warranty_years) != len(set(warranty_years)):
        raise CostConfigurationError("coating warranty years must be unique and ordered from shortest to longest")

    confidence = _mapping(config.get("confidence"), "cost_estimation.confidence")
    confidence_base = _number(confidence.get("base_score"), "cost_estimation.confidence.base_score")
    confidence_minimum = _number(confidence.get("minimum_score"), "cost_estimation.confidence.minimum_score")
    confidence_maximum = _number(confidence.get("maximum_score"), "cost_estimation.confidence.maximum_score")
    if confidence_minimum > confidence_base or confidence_base > confidence_maximum:
        raise CostConfigurationError("confidence scores must satisfy minimum <= base <= maximum")
    raw_adjustments = _mapping(confidence.get("adjustments"), "cost_estimation.confidence.adjustments")
    expected_adjustments = set(CostConfidenceInputs.__dataclass_fields__)
    if set(raw_adjustments) != expected_adjustments:
        missing = sorted(expected_adjustments - set(raw_adjustments))
        extra = sorted(set(raw_adjustments) - expected_adjustments)
        raise CostConfigurationError(f"confidence adjustments do not match inputs; missing={missing}, extra={extra}")
    confidence_adjustments = {
        field: _number(weight, f"cost_estimation.confidence.adjustments.{field}")
        for field, weight in raw_adjustments.items()
    }

    disclaimer = str(config.get("report_disclaimer", "")).strip()
    if not disclaimer:
        raise CostConfigurationError("cost_estimation.report_disclaimer is required")

    return CostEstimationConfig(
        score_minimum=score_minimum,
        score_maximum=score_maximum,
        replacement_tiers=replacement_tiers,
        replacement_contingency_percentage=replacement_contingency,
        replacement_components=replacement_components,
        overlay_tiers=overlay_tiers,
        overlay_contingency_percentage=overlay_contingency,
        coating_warranty_options=tuple(coating_warranty_options),
        confidence_base_score=confidence_base,
        confidence_minimum_score=confidence_minimum,
        confidence_maximum_score=confidence_maximum,
        confidence_adjustments=confidence_adjustments,
        report_disclaimer=disclaimer,
    )


COST_ESTIMATION_CONFIG = load_cost_estimation_config()


def _rate_for_condition(
    roof_condition_score: float,
    tiers: tuple[RateTier, ...],
    config: CostEstimationConfig,
) -> float:
    score = clamp(float(roof_condition_score), config.score_minimum, config.score_maximum)
    for tier in tiers:
        matches = score >= tier.minimum_score if tier.minimum_inclusive else score > tier.minimum_score
        if matches:
            return tier.cost_per_sqft
    raise CostConfigurationError(f"No pricing tier covers roof-condition score {score}")


def cost_per_sqft_for_condition(
    roof_condition_score: float,
    config: CostEstimationConfig | None = None,
) -> float:
    active_config = config or COST_ESTIMATION_CONFIG
    return _rate_for_condition(roof_condition_score, active_config.replacement_tiers, active_config)


def overlay_cost_per_sqft_for_condition(
    roof_condition_score: float,
    config: CostEstimationConfig | None = None,
) -> float:
    active_config = config or COST_ESTIMATION_CONFIG
    return _rate_for_condition(roof_condition_score, active_config.overlay_tiers, active_config)


def confidence_score(
    inputs: CostConfidenceInputs | None = None,
    config: CostEstimationConfig | None = None,
) -> int:
    active_config = config or COST_ESTIMATION_CONFIG
    inputs = inputs or CostConfidenceInputs()
    score = active_config.confidence_base_score
    for field, weight in active_config.confidence_adjustments.items():
        if getattr(inputs, field):
            score += weight
    return round(clamp(score, active_config.confidence_minimum_score, active_config.confidence_maximum_score))


def estimate_roof_replacement_cost(
    roof_condition_score: float,
    roof_area_sqft: float,
    confidence_inputs: CostConfidenceInputs | None = None,
    config: CostEstimationConfig | None = None,
) -> RoofReplacementEstimate:
    active_config = config or COST_ESTIMATION_CONFIG
    area = float(roof_area_sqft)
    if area < 0:
        raise ValueError("roof_area_sqft must be greater than or equal to zero")

    score = clamp(float(roof_condition_score), active_config.score_minimum, active_config.score_maximum)
    rate = cost_per_sqft_for_condition(score, active_config)
    overlay_rate = overlay_cost_per_sqft_for_condition(score, active_config)
    subtotal = area * rate
    overlay_subtotal = area * overlay_rate
    component_costs = {
        component: round(subtotal * percentage, 2)
        for component, percentage in active_config.replacement_components.items()
    }
    contingency = subtotal * active_config.replacement_contingency_percentage
    overlay_contingency = overlay_subtotal * active_config.overlay_contingency_percentage

    return RoofReplacementEstimate(
        roof_condition_score=score,
        roof_area_sqft=area,
        cost_per_sqft=rate,
        overlay_cost_per_sqft=overlay_rate,
        replacement_subtotal=round(subtotal, 2),
        overlay_subtotal=round(overlay_subtotal, 2),
        overlay_contingency_cost=round(overlay_contingency, 2),
        overlay_total_project_cost=round(overlay_subtotal + overlay_contingency, 2),
        component_costs=component_costs,
        contingency_percentage=active_config.replacement_contingency_percentage,
        overlay_contingency_percentage=active_config.overlay_contingency_percentage,
        contingency_cost=round(contingency, 2),
        total_project_cost=round(subtotal + contingency, 2),
        confidence_score=confidence_score(confidence_inputs, active_config),
    )


def estimate_roof_coating_cost(
    roof_area_sqft: float,
    config: CostEstimationConfig | None = None,
) -> RoofCoatingEstimate:
    active_config = config or COST_ESTIMATION_CONFIG
    area = float(roof_area_sqft)
    if area < 0:
        raise ValueError("roof_area_sqft must be greater than or equal to zero")
    return RoofCoatingEstimate(
        roof_area_sqft=area,
        warranty_options=tuple(
            CoatingWarrantyEstimate(
                years=option.years,
                minimum_cost_per_sqft=option.minimum_cost_per_sqft,
                maximum_cost_per_sqft=option.maximum_cost_per_sqft,
                minimum_total_cost=round(area * option.minimum_cost_per_sqft, 2),
                maximum_total_cost=round(area * option.maximum_cost_per_sqft, 2),
            )
            for option in active_config.coating_warranty_options
        ),
    )


def cost_estimation_disclaimer(config: CostEstimationConfig | None = None) -> str:
    return (config or COST_ESTIMATION_CONFIG).report_disclaimer


if __name__ == "__main__":
    example = estimate_roof_replacement_cost(
        roof_condition_score=57,
        roof_area_sqft=357_749,
        confidence_inputs=CostConfidenceInputs(
            roof_type_confidently_identified=True,
            roof_area_accurately_measured=True,
            building_footprint_available=True,
            high_resolution_imagery_available=True,
        ),
    )
    print(example.to_dict())
