---
status: active
---

# Cost Estimation

## Purpose

This document describes the current factors, pricing tiers, and formulas used to produce preliminary commercial roof replacement, overlay, and coating cost estimates.

The `cost_estimation` YAML block below is the operational source for pricing, contingencies, component allocations, confidence weights, and the report disclaimer. The validated formulas remain implemented in `roof_replacement_cost_estimator.py`.

## Runtime Configuration

The report generator loads this block when the cost-estimator module starts. Keep the `cost_estimation` label on the opening YAML fence so the configuration loader can identify it, and restart any long-running report process after changing these values. The loader uses PyYAML's safe YAML parser.

```yaml cost_estimation
schema_version: 1

score_range:
  minimum: 0
  maximum: 100

replacement:
  contingency_percentage: 0.15
  pricing_tiers:
    - minimum_score: 90
      minimum_inclusive: true
      cost_per_sqft: 21.00
    - minimum_score: 80
      minimum_inclusive: true
      cost_per_sqft: 21.50
    - minimum_score: 75
      minimum_inclusive: true
      cost_per_sqft: 22.00
    - minimum_score: 70
      minimum_inclusive: true
      cost_per_sqft: 22.75
    - minimum_score: 65
      minimum_inclusive: true
      cost_per_sqft: 23.50
    - minimum_score: 60
      minimum_inclusive: true
      cost_per_sqft: 24.50
    - minimum_score: 55
      minimum_inclusive: true
      cost_per_sqft: 25.50
    - minimum_score: 50
      minimum_inclusive: true
      cost_per_sqft: 26.75
    - minimum_score: 45
      minimum_inclusive: true
      cost_per_sqft: 28.00
    - minimum_score: 40
      minimum_inclusive: false
      cost_per_sqft: 28.50
    - minimum_score: 0
      minimum_inclusive: true
      cost_per_sqft: 29.00
  components:
    tear_off_and_disposal:
      label: Tear Off & Disposal
      percentage: 0.14
    roof_membrane:
      label: Roof Membrane
      percentage: 0.28
    insulation:
      label: Insulation
      percentage: 0.17
    flashing_and_edging:
      label: Flashing/Edging
      percentage: 0.11
    labor:
      label: Labor
      percentage: 0.30

overlay:
  contingency_percentage: 0.10
  pricing_tiers:
    - minimum_score: 76
      minimum_inclusive: true
      cost_per_sqft: 9.00
    - minimum_score: 71
      minimum_inclusive: true
      cost_per_sqft: 9.25
    - minimum_score: 66
      minimum_inclusive: true
      cost_per_sqft: 9.50
    - minimum_score: 61
      minimum_inclusive: true
      cost_per_sqft: 9.75
    - minimum_score: 56
      minimum_inclusive: true
      cost_per_sqft: 10.00
    - minimum_score: 51
      minimum_inclusive: true
      cost_per_sqft: 10.25
    - minimum_score: 46
      minimum_inclusive: true
      cost_per_sqft: 10.50
    - minimum_score: 40
      minimum_inclusive: true
      cost_per_sqft: 11.00
    - minimum_score: 0
      minimum_inclusive: true
      cost_per_sqft: 12.00

coating:
  warranty_options:
    - years: 10
      minimum_cost_per_sqft: 3.50
      maximum_cost_per_sqft: 4.00
    - years: 15
      minimum_cost_per_sqft: 4.50
      maximum_cost_per_sqft: 5.00
    - years: 20
      minimum_cost_per_sqft: 5.50
      maximum_cost_per_sqft: 6.00

confidence:
  base_score: 70
  minimum_score: 50
  maximum_score: 100
  adjustments:
    roof_type_confidently_identified: 8
    roof_area_accurately_measured: 10
    building_footprint_available: 6
    high_resolution_imagery_available: 6
    shadows_obscure_roof: -7
    tree_coverage_obscures_roof: -8
    image_resolution_poor: -10
    roof_edges_hidden: -8

report_disclaimer: >-
  Cost estimates are derived from publicly available information and proprietary commercial roofing analysis models and are intended for preliminary budgeting and planning purposes only. Roof-area measurements do not include the vertical surface area of parapet walls. They should not be considered a contractor quote, engineering assessment, or guarantee of actual project costs. Estimates do not include additional repairs or unforeseen conditions that may be identified during an on-site inspection.
```

## Common Estimate Inputs

The cost-estimation process uses the following primary inputs:

- Roof area in square feet, currently derived from the available building-footprint area
- Overall roof-condition score, constrained to a range of 0 through 100
- Cost-confidence factors describing the completeness and quality of the available property and imagery data

For replacement and overlay estimates, the roof-condition score selects the applicable base cost per square foot. The selected rate is multiplied by the roof area, and the appropriate contingency is then added. Each coating warranty estimate applies its configured minimum and maximum rates to the roof area.

## Roof Replacement Cost Estimate

Replacement pricing tiers and the contingency percentage are defined in the runtime configuration above. Lower condition scores use higher budgetary rates to account for the increased likelihood of deterioration, difficult tear-off conditions, damaged insulation, substrate repairs, and related replacement complexity. These conditions are represented through the rate tiers and contingency; they are not separately itemized as additional repairs.

### Replacement Formula

```text
Replacement subtotal = roof area SF x replacement rate per SF
Replacement contingency = replacement subtotal x configured replacement contingency percentage
Total replacement estimate = replacement subtotal + replacement contingency
```

### Replacement Cost Allocation

The replacement subtotal is allocated among the conceptual cost components and percentages defined in the runtime configuration. These allocations provide a standardized cost breakdown. They do not currently change the total estimate because each component is calculated as a portion of the previously calculated replacement subtotal.

## Roof Overlay Cost Estimate

Overlay pricing tiers and the contingency percentage are defined in the runtime configuration above. Lower condition scores use higher overlay rates to reflect the increased likelihood of preparation, localized repairs, flashing work, and other corrective work before an overlay can be installed.

### Overlay Formula

```text
Overlay subtotal = roof area SF x overlay rate per SF
Overlay contingency = overlay subtotal x configured overlay contingency percentage
Total overlay estimate = overlay subtotal + overlay contingency
```

An overlay estimate is a preliminary budgeting scenario, not a determination that the existing roof is suitable for an overlay. Field verification is required to evaluate moisture, insulation, deck condition, attachment, drainage, existing roof layers, code requirements, and manufacturer-system requirements.

## Roof Coating Cost Estimate

The coating warranty terms and their minimum and maximum rates are defined in the runtime configuration above.

### Coating Formula

```text
Minimum warranty estimate = roof area SF x configured warranty minimum coating rate
Maximum warranty estimate = roof area SF x configured warranty maximum coating rate
```

Each coating warranty range is a preliminary budget scenario and does not guarantee that a specific roof qualifies for a coating system or manufacturer warranty.

## Cost-Confidence Factors

The estimator calculates a separate confidence score using the base score, boundaries, and positive or negative adjustments defined in the runtime configuration. Confidence does not currently change the replacement, overlay, or coating price; it communicates the reliability of the available inputs.

## Current Exclusions and Limitations

The current calculations do not explicitly adjust pricing for:

- Geographic labor or material-cost differences
- Roof-system or membrane type
- Roof height, access, staging, cranes, or occupied-building constraints
- Deck replacement or structural repairs
- Wet insulation or moisture-remediation quantities
- Asbestos, hazardous materials, or environmental abatement
- Permit, engineering, bonding, tax, or insurance requirements
- Drainage redesign or major mechanical and electrical work
- Market escalation, contractor availability, or project schedule
- Manufacturer-specific assemblies or warranty requirements

## Report Disclaimer

The report disclaimer is defined once in the runtime configuration and displayed at the bottom of the Roof Repair Options card.
