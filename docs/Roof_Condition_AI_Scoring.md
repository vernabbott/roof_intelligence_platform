# Roof Condition AI Scoring Specification

**Project:** PilotPoint IQ Roof Intelligence  
**Document Version:** 1.0  
**Status:** Design Specification  
**Last Updated:** July 2026

---

# Objective

Improve the AI Roof Condition scoring model by evaluating observable roof characteristics from aerial and overhead imagery, geospatial information, publicly available property records, and computer vision analysis.

The goal is **not** to replace an on-site inspection.

The goal is to provide contractors with actionable commercial roofing intelligence by estimating:

- Roof Type
- Roof Condition
- Likelihood of Repairs
- Likelihood of Replacement
- Opportunity Score

The scoring model should estimate the overall roof condition using only observable characteristics.

---

# Roof Condition Score

The roof condition score ranges from **0–100**.

| Score | Condition |
|--------|-----------|
| 90-100 | Excellent |
| 80-89 | Very Good |
| 70-79 | Good |
| 60-69 | Fair |
| 50-59 | Fair / Poor |
| 40-49 | Poor |
| Below 40 | Critical |

Scores below 40 should generally indicate roofs that are likely candidates for replacement rather than overlay.

---

# Universal Roof Indicators

These conditions apply to every roof type.

## Ponding Water

Priority: Critical

Indicators:

- Standing water
- Water staining
- Dark wet areas
- Persistent low spots
- Water around rooftop equipment
- Water near drains

Influence:

Large negative impact on condition score.

---

## Drainage

Priority: High

Indicators:

- Blocked roof drains
- Debris around drains
- Overflow staining
- Sediment accumulation
- Poor roof slope

---

## Flashing

Priority: High

Indicators:

- Damaged flashing
- Loose flashing
- Missing flashing
- Open flashing seams
- Flashing deterioration around penetrations

---

## Rooftop Equipment

Priority: Medium

Indicators:

- Heavy rooftop traffic
- Damaged walk pads
- Numerous penetrations
- Abandoned equipment
- Poorly sealed curbs

---

## Debris

Priority: Medium

Indicators:

- Leaves
- Dirt accumulation
- Branches
- Trash
- Wind-blown debris

---

## Vegetation

Priority: High

Indicators:

- Moss
- Grass
- Weeds
- Trees
- Biological growth

Vegetation usually indicates chronic moisture.

---

# TPO Roofs

## High Priority Indicators

### Ponding Water

Critical

### Open Seams

Critical

### Torn Membrane

Critical

### Exposed Insulation

Critical

### Flashing Failure

High

### Punctures

High

---

## Medium Priority Indicators

- Surface discoloration
- Wrinkles
- Membrane buckling
- Fishmouths
- Surface wear
- Traffic wear

---

## Low Priority Indicators

- General weathering
- Minor dirt accumulation
- Slight fading

---

# EPDM Roofs

## High Priority Indicators

- Membrane shrinkage
- Open seams
- Pullback from walls
- Flashing stress
- Ponding water
- Punctures

---

## Medium Priority

- Surface chalking
- Wrinkles
- Patch repairs
- Membrane distortion

---

## Low Priority

- Minor discoloration
- Normal weathering

---

# PVC Roofs

## High Priority

- Open seams
- Tears
- Ponding
- Flashing failure
- Exposed reinforcement

---

## Medium Priority

- Surface discoloration
- Weld deterioration
- Wrinkling
- Heavy rooftop traffic

---

## Low Priority

- Dirt
- Normal fading

---

# Modified Bitumen

## High Priority

- Splits
- Cracks
- Ponding
- Blisters
- Exposed reinforcement
- Flashing failure

---

## Medium Priority

- Granule loss
- Surface erosion
- Previous repairs

---

## Low Priority

- General weathering

---

# Built-Up Roof (Tar & Gravel)

## High Priority

- Exposed asphalt
- Gravel loss
- Blisters
- Cracks
- Ponding
- Significant patching

---

## Medium Priority

- Uneven gravel
- Surface erosion
- Discoloration

---

## Low Priority

- Minor gravel displacement

---

# Ballasted Roof

## High Priority

- Missing ballast
- Exposed membrane
- Ponding
- Drain blockage

---

## Medium Priority

- Uneven ballast
- Vegetation
- Displaced pavers

---

## Low Priority

- Minor ballast movement

---

# Metal Roof

## High Priority

- Corrosion
- Rust
- Open seams
- Loose fasteners
- Missing fasteners
- Bent panels
- Flashing failure

---

## Medium Priority

- Coating deterioration
- Minor oxidation
- Sealant failure

---

## Low Priority

- Surface dirt
- Cosmetic fading

---

# Category Weights

The overall roof condition score should be influenced by the following categories.

| Category | Weight |
|----------|-------:|
| Ponding & Drainage | 25% |
| Membrane / Surface Integrity | 25% |
| Flashing & Penetrations | 20% |
| Surface Wear & Weathering | 15% |
| Repairs & Patching | 10% |
| Debris / Vegetation | 5% |

The weighting may be adjusted depending on roof type.

---

# AI Output

The AI should produce:

- Roof Type
- Roof Condition Score
- Confidence Score
- Estimated Remaining Service Life
- Recommended Action
- Key Observed Conditions

Example:

Observed Conditions

• Moderate ponding near central drains

• Membrane wrinkling around rooftop HVAC

• Surface discoloration consistent with UV aging

• Flashing deterioration at multiple penetrations

• Debris accumulation affecting drainage

---

# Design Philosophy

The AI should prioritize identifying roofs that represent high-value commercial roofing opportunities.

The objective is to assist roofing contractors in prioritizing sales efforts and identifying buildings that warrant further evaluation and on-site inspection.

The analysis should remain conservative and avoid overstating damage when confidence is low.

Whenever uncertainty exists, the system should lower the confidence score rather than making aggressive assumptions.