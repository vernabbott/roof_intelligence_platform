---
status: active
---

# Roof Information

## Purpose

This document controls how roofing-surface conclusions and physical roof configuration are presented in the Roof Information card.

## Runtime Configuration

```yaml roof_information
schema_version: 1

display:
  primary_prefix: "Primary:"
  secondary_prefix: "Secondary:"
  maximum_secondary_types: 3
  minimum_secondary_confidence: 45
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
  Treat roofing surfaces and physical roof configuration as separate conclusions. Roof Type contains only the dominant supported roofing surface as Primary and adds Secondary when a materially distinct secondary surface is visibly supported. Do not add a Secondary material from color variation alone when the same field, seams, edges, slope, elevation, and construction remain continuous; treat mottling and discoloration as condition evidence. Derive the displayed material from the same zone evidence used for Roof Observations; never make a more specific material claim than the observations support. Use White Single-Ply or Coated Roof when a smooth light-colored surface cannot be separated among TPO, PVC, and a coating, including when aging or weathering obscures the distinguishing details. Use Modified Bitumen, Coated Roof, or Tar and Gravel when a tan weathered low-slope field supports those three alternatives but roll laps, coating application evidence, and embedded aggregate remain unresolved. Do not identify air-conditioning units, equipment housings, curbs, coping, caps, edge trim, mechanical screens, solar panels, or skylights as roofing-surface types. On ribbed metal roofs, an organized array of same-size narrow rectangular translucent panels aligned with the ribs may establish fiberglass skylights even without prominent curbs; distinguish them from isolated patches, coating wear, shadows, or artifacts. Do not display material-confidence or area percentages. Use controlled ambiguity wording when imagery cannot support one material. Combine PVC and coating as PVC or Coated Roof; never expose standalone PVC or Coated Roof. Use Ballasted or Tar and Gravel only when an aggregate surface is established but its assembly cannot be resolved. Roof System describes physical configuration only: single or multiple connected roof sections, single or multiple slopes and slope form, and the visible presence of A/C units, solar panels, and skylights. Never assess or display parapet walls from overhead aerial imagery. Do not place roofing-material names in Roof System.
```

## Card Rules

- `Roof Type` is the roofing-surface conclusion shown on the card.
- Format Roof Type as `Primary: <type>` and add `; Secondary: <type(s)>` only when distinct secondary roof surfaces are sufficiently supported.
- `Roof System` describes physical roof configuration and rooftop features, not roofing materials.
- Roof System states whether the target has single or multiple connected sections, single or multiple slopes, slope form, and whether A/C units, solar panels, and skylights are visible.
- Do not assess or display parapet walls because the overhead aerial view does not establish them reliably.
- Do not show the former `Possible Types` row.
- Do not display confidence or roof-area percentages beside roof materials.
- Display PVC and coated roofing only as the controlled combined label `PVC or Coated Roof`; never expose either as a standalone aerial result.
- Display `Ballasted or Tar and Gravel` when the aggregate surface is established but the imagery cannot resolve which assembly is present.
- Display `White Single-Ply or Coated Roof` when the imagery shows a distinct smooth light-colored surface but cannot resolve TPO, PVC, or a coating.
- Do not create or display a secondary material solely from within-field color variation; require a construction boundary or non-color material evidence.
- Report fiberglass skylights as present when repeated same-size translucent rectangular panels form an organized array aligned with a metal roof's ribs. If silicone restoration is discussed, require masking and exclusion of the light-transmitting panel faces.
- Keep the overall AI confidence field because it describes the analysis as a whole, not a roof-material percentage.
- Keep Roof Type, Visible Concerns, Roof Age Estimate, Roof Area, Roof Pitch, and overall Confidence.

## Interpretation

Examples:

```text
Roof Type — Primary: Ballasted
Roof Type — Primary: TPO
Roof Type — Primary: Metal; Secondary: TPO
Roof System — Multiple connected roof sections; multiple low-slope planes; A/C units present; no solar panels visible; skylights present
```

When low-confidence candidates conflict with a well-supported primary type, omit them from the card. Preserve their evidence in the analysis JSON for audit purposes.
