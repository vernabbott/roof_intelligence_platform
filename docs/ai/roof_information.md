---
status: active
---

# Roof Information

## Purpose

This document controls how roof-material conclusions are presented in the Roof Information card. The card must provide one consistent material statement without displaying numeric material-confidence percentages or a separate Possible Types row.

## Runtime Configuration

```yaml roof_information
schema_version: 1

display:
  primary_prefix: "Primary:"
  secondary_prefix: "Secondary:"
  maximum_secondary_types: 3
  minimum_secondary_confidence: 60
  show_possible_types_row: false
  show_material_percentages: false

component_exclusions:
  - rooftop cap
  - enclosure
  - equipment housing
  - mechanical screen
  - coping
  - edge trim
  - parapet trim
  - penthouse-like appendage
  - canopy-like attachment
  - roof strip

ai_guidance: >-
  Treat roof fields and rooftop components separately. Do not identify air-conditioning units, equipment housings, curbs, coping, caps, edge trim, mechanical screens, or other rooftop components as secondary roof materials. Establish one primary roof material for the dominant supported roof field. Include a secondary roof material only when a materially distinct roof field is visibly supported; do not add a secondary type merely because it is a low-confidence possibility. Do not place numeric material-confidence or roof-material-area percentages in roof_system. Use controlled ambiguity wording when the imagery cannot support choosing one material. For standard aerial reports, combine PVC and coating as PVC or Coated Roof; never expose standalone PVC or Coated Roof. Use Ballasted or Tar and Gravel when a tan aggregate-covered roof is visible but perimeter stone transitions and embedment cannot be resolved.
```

## Card Rules

- `Roof System` is the single material conclusion shown on the card.
- Format it as `Primary: <type>` and add `; Secondary: <type(s)>` only when distinct secondary roof fields are sufficiently supported.
- Do not show the former `Possible Types` row.
- Do not display confidence or roof-area percentages beside roof materials.
- Display PVC and coated roofing only as the controlled combined label `PVC or Coated Roof`; never expose either as a standalone aerial result.
- Display `Ballasted or Tar and Gravel` when the aggregate surface is established but the imagery cannot resolve which assembly is present.
- Keep the overall AI confidence field because it describes the analysis as a whole, not a roof-material percentage.
- Keep Roof Type, Visible Concerns, Roof Age Estimate, Roof Area, Roof Pitch, and overall Confidence.

## Interpretation

Examples:

```text
Primary: Ballasted
Primary: TPO
Primary: Metal; Secondary: TPO
Primary: TPO; Secondary: EPDM or Modified Bitumen
Primary: PVC or Coated Roof
Primary: Ballasted or Tar and Gravel
```

When low-confidence candidates conflict with a well-supported primary type, omit them from the card. Preserve their evidence in the analysis JSON for audit purposes.
