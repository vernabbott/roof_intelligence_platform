#!/usr/bin/env python3
"""Reusable roof replacement cost estimator."""

from __future__ import annotations

from dataclasses import asdict, dataclass


COMPONENT_PERCENTAGES = {
    "Tear Off & Disposal": 0.14,
    "Roof Membrane": 0.28,
    "Insulation": 0.17,
    "Flashing/Edging": 0.11,
    "Labor": 0.30,
}

CONTINGENCY_PERCENTAGE = 0.15
OVERLAY_CONTINGENCY_PERCENTAGE = 0.10

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


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def cost_per_sqft_for_condition(roof_condition_score: float) -> float:
    score = clamp(float(roof_condition_score), 0, 100)
    if score >= 90:
        return 21.00
    if score >= 80:
        return 21.50
    if score >= 75:
        return 22.00
    if score >= 70:
        return 22.75
    if score >= 65:
        return 23.50
    if score >= 60:
        return 24.50
    if score >= 55:
        return 25.50
    if score >= 50:
        return 26.75
    if score >= 45:
        return 28.00
    if score > 40:
        return 28.50
    return 29.00


def overlay_cost_per_sqft_for_condition(roof_condition_score: float) -> float:
    score = clamp(float(roof_condition_score), 0, 100)
    if score >= 76:
        return 9.00
    if score >= 71:
        return 9.25
    if score >= 66:
        return 9.50
    if score >= 61:
        return 9.75
    if score >= 56:
        return 10.00
    if score >= 51:
        return 10.25
    if score >= 46:
        return 10.50
    if score >= 40:
        return 11.00
    return 12.00


def confidence_score(inputs: CostConfidenceInputs | None = None) -> int:
    if inputs is None:
        inputs = CostConfidenceInputs()

    score = 70
    positive_weights = {
        "roof_type_confidently_identified": 8,
        "roof_area_accurately_measured": 10,
        "building_footprint_available": 6,
        "high_resolution_imagery_available": 6,
    }
    negative_weights = {
        "shadows_obscure_roof": -7,
        "tree_coverage_obscures_roof": -8,
        "image_resolution_poor": -10,
        "roof_edges_hidden": -8,
    }

    for field, weight in positive_weights.items():
        if getattr(inputs, field):
            score += weight
    for field, weight in negative_weights.items():
        if getattr(inputs, field):
            score += weight

    return round(clamp(score, 50, 100))


def estimate_roof_replacement_cost(
    roof_condition_score: float,
    roof_area_sqft: float,
    confidence_inputs: CostConfidenceInputs | None = None,
) -> RoofReplacementEstimate:
    area = float(roof_area_sqft)
    if area < 0:
        raise ValueError("roof_area_sqft must be greater than or equal to zero")

    score = clamp(float(roof_condition_score), 0, 100)
    rate = cost_per_sqft_for_condition(score)
    overlay_rate = overlay_cost_per_sqft_for_condition(score)
    subtotal = area * rate
    overlay_subtotal = area * overlay_rate
    component_costs = {
        component: round(subtotal * percentage, 2)
        for component, percentage in COMPONENT_PERCENTAGES.items()
    }
    contingency = subtotal * CONTINGENCY_PERCENTAGE
    overlay_contingency = overlay_subtotal * OVERLAY_CONTINGENCY_PERCENTAGE

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
        contingency_percentage=CONTINGENCY_PERCENTAGE,
        overlay_contingency_percentage=OVERLAY_CONTINGENCY_PERCENTAGE,
        contingency_cost=round(contingency, 2),
        total_project_cost=round(subtotal + contingency, 2),
        confidence_score=confidence_score(confidence_inputs),
    )


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
