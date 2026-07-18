---
status: active
---

# Roof Type Classification

## Purpose

This document is the central decision framework for AI roof-type classification. When the roof-reference feature is enabled, Stage 1 uses this guide to divide a building into visible roof zones and select candidate roof systems. Stage 2 uses the detailed guides and positive images listed in the roof-reference manifest to make the final comparison.

Roof type and roof condition are separate decisions. Do not classify a material from damage, staining, age, or assumed building use alone.

## Supported Candidate Keys

- `tpo` — thermoplastic polyolefin single-ply membrane
- `pvc` — Stage 1 candidate for polyvinyl chloride single-ply membrane; do not expose as a standalone final aerial result
- `epdm` — synthetic-rubber single-ply membrane
- `ballasted` — stone- or paver-ballasted low-slope roof; underlying membrane may be unknown
- `metal` — standing-seam, ribbed, corrugated, or other metal panels
- `mod_bit` — modified-bitumen or likely asphaltic roll roofing
- `tar_and_gravel` — aggregate-surfaced built-up roofing, commonly called tar and gravel
- `coating` — Stage 1 candidate for a reflective or asphaltic coating; do not expose as a standalone final aerial result
- `pvc_or_coating` — required final-stage result when aerial imagery favors PVC/coating over TPO but cannot separate PVC membrane from a coated roof
- `epdm_or_mod_bit` — controlled final-stage ambiguity when a dark membrane cannot be separated between EPDM and modified bitumen
- `mod_bit_or_coating` — controlled final-stage ambiguity when a weathered asphaltic roof cannot be separated between modified bitumen and coating
- `mod_bit_or_tar_and_gravel` — controlled final-stage ambiguity when an asphaltic or aggregate-looking roof cannot be separated between modified bitumen and tar-and-gravel/BUR
- `unknown` — evidence is insufficient to establish a material family

## Classification Workflow

1. Confirm the visible surface is part of the target building roof.
2. Divide the roof into contiguous zones using parapets, ridges, expansion joints, elevation changes, additions, and material transitions.
   Do not create roof-material zones for parapet coping, edge trim, curbs, equipment housings, mechanical screens, or other rooftop components that are not roof fields.
3. Evaluate each zone independently for surface texture, color, reflectivity, seam or panel geometry, edge details, flashings, aggregate, and penetrations.
4. Return as many as three evidence-supported candidates per zone. Do not include unsupported possibilities merely because they are common.
5. Return only a supported canonical type key. For an unresolved white membrane or reflective roof, use `tpo` as the conservative default and preserve PVC or coating as alternatives.
6. Assign confidence to each candidate based on visible evidence, resolution, angle, obstruction, lighting, and remaining alternatives.
7. Treat estimated area percentages as approximate. Use `0` when the visible share cannot be estimated responsibly.

## Image Quality And Confidence

- Judge image quality before assigning material confidence. Consider sharpness, compression, pixelation, glare, shadow, obstruction, and whether the distinguishing seams, ribs, edges, texture, or application pattern are actually resolved.
- Never use high material confidence when the image is too soft or compressed to resolve the cues that distinguish the selected type from its closest alternatives.
- When only the material family is supportable from roof-scale geometry but profile, seam, or surface details are unresolved, keep zone confidence at 60 or below and state the image limitation.
- When the image does not resolve enough non-color evidence to establish even the material family, use `unknown` or a controlled ambiguity label rather than pairing a guess with high confidence.
- Overall AI confidence must reflect the weakest material decision displayed in Roof Information. It must not exceed 60 when the primary roof material is based on unresolved details in poor imagery.

## Cross-Material Cues

| Candidate | Supporting aerial cues | Important ambiguity |
| --- | --- | --- |
| TPO | White-to-cream smooth field, broad sheets, visible welded laps, matching flashings | Often indistinguishable from PVC or a coating |
| PVC | Bright or uniform white/gray field, broad sheets, smooth thermoplastic appearance | Often indistinguishable from TPO |
| EPDM | Black or charcoal smooth field, broad sheets, low-profile lap grid, dark flashings | Can resemble smooth modified bitumen or a dark coating |
| Ballasted | Loose stone or pavers with visible depth and intentional distribution; at lower resolution, a tan or beige mottled field with a lighter/coarser perimeter band | Hidden membrane cannot normally be identified; may resemble gravel BUR or a uniformly coated roof when individual stones are unresolved |
| Metal | Repeated raised ribs, rigid planes, directional sheen, crisp ridges and edge trim | Membrane attachment rows may resemble ribs at poor resolution |
| Modified bitumen | Dark or granular field, frequent narrow parallel roll laps, staggered end joints | Can resemble EPDM, smooth BUR, or coated asphalt roofing |
| Tar and gravel/BUR | Fine embedded-looking aggregate, uniform field, no exposed sheet-lap grid | Can be indistinguishable from a loose-ballasted membrane roof |
| Coating | Roller or spray variation, old seams and repairs showing through, one finish spanning different substrates | New coating can resemble a new single-ply membrane |

## Required Ambiguity Rules

- Use `tpo` when a white or light-colored membrane-like roof cannot be reliably separated among TPO, PVC, and coating from the available imagery. Lower confidence and retain `pvc` and/or `coating` as alternatives.
- Do not return standalone `pvc` or `coating` as a final aerial classification. Use `pvc_or_coating`, displayed as **PVC or Coated Roof**, whenever the imagery favors that family over TPO but cannot prove whether the exposed surface is PVC membrane or a coating.
- Close visual details, readable markings, specifications, or other non-aerial records may support exact PVC or coating identification during a separate verification workflow, but the standard aerial report must retain the combined result.
- A highly weathered coating may appear patchy, chalky, tan, gray, or uneven rather than uniformly white. Favor `pvc_or_coating` over TPO when a monolithic finish shows irregular application variation, old repairs or substrate details telegraphing through, and localized wear-through without a consistent membrane-sheet layout.
- Apply the TPO default only to a genuinely smooth, membrane-like white or light roof. Do not apply it to a patchy, heavily weathered, asphaltic-looking, or aggregate-textured surface merely because sun exposure makes portions appear light.
- Use `epdm_or_mod_bit`, displayed as **EPDM or Modified Bitumen**, when a dark membrane is established but width, seams, and texture do not support choosing between those two systems.
- Use `mod_bit_or_coating`, displayed as **Modified Bitumen or Coated Roof**, when a weathered asphaltic-looking surface is established but coating-specific evidence and roll-lap details remain unresolved.
- Use `mod_bit_or_tar_and_gravel`, displayed as **Modified Bitumen or Tar and Gravel**, when the image suggests an asphaltic or aggregate surface but cannot resolve roll laps, stone embedment, or loose ballast well enough to choose one.
- Use `aggregate-surfaced low-slope roof (BUR vs ballasted membrane indeterminate)` when stone embedment and the underlying assembly cannot be established.
- Use `unknown/indeterminate roof type` rather than forcing a candidate from color alone.
- Return the canonical type `metal` whenever metal is supported. Describe a subtype such as standing seam, ribbed, or corrugated only in supporting observations, and only when the profile is clearly resolved.
- Do not classify a dark low-slope zone as metal from faint parallel lines or apparent panel divisions alone. Require clear rigid planes, repeated raised ribs with consistent shadows, or metal edge/ridge detailing. If those cues are unresolved and the surface is plausibly a dark membrane, prefer `epdm`, `mod_bit`, or `epdm_or_mod_bit` with metal retained only as an alternative.
- In soft overhead imagery, a dense, regular, full-field pattern of narrow parallel panel lines combined with rigid rectangular geometry and crisp perimeter construction may support generic `metal` at low-to-moderate confidence even when rib height and attachment are unresolved. This exception does not support a metal subtype.
- A dark, flat, matte attached field with broad membrane character and no resolved raised-rib shadows or metal edge construction favors EPDM over metal, even when faint straight lines are present.

## Mixed-Roof Requirements

- Do not collapse visibly different zones into one whole-building material.
- Give every zone a stable identifier, location description, confidence, supporting cues, alternatives, limitations, and approximate visible-area percentage.
- The whole-building classification must be `mixed` when more than one materially different roof system is visible.
- Small metal canopies, membrane additions, rooftop penthouses, and paver terraces should remain separate when their construction differs from the main roof.
- Do not let a dominant roof type absorb a smaller attached section. A small zone with different color, texture, seam frequency, or boundary geometry must be evaluated separately, including narrow modified-bitumen sections beside a larger TPO roof.
- A small tan, gray, or weathered attached roof section may be modified bitumen even when roll laps are below aerial resolution. If its tone, weathering, boundary, or surface character differs from an adjacent TPO field, keep it separate and compare modified bitumen before extending the TPO classification into it.
- A dominant tan, matte, weathered asphaltic field may also be modified bitumen when individual roll laps fall below image resolution. Visible wear, patching, an asphaltic surface character, and a clear contrast with an adjacent smooth white TPO zone are stronger combined evidence than seam absence alone.

## Out-of-Scope Roofs

- The current reference library is focused on the supported low-slope systems and metal.
- A clearly pitched, granular asphalt-shingle roof is outside this reference set. Return `unknown` with an out-of-scope limitation; do not relabel shingles as modified bitumen merely because both are asphalt-based.
- Out-of-scope buildings should be excluded from roof-reference accuracy pilots unless they are intentionally included as negative controls.

## Positive Identification Guides

- [TPO](roof_reference_library/tpo/tpo_roof_identification.md)
- [PVC](roof_reference_library/pvc/pvc_roof_identification.md)
- [EPDM](roof_reference_library/epdm/epdm_roof_identification.md)
- [Ballasted](roof_reference_library/ballasted/ballasted_roof_identification.md)
- [Metal](roof_reference_library/metal/metal_roof_identification.md)
- [Modified bitumen](roof_reference_library/mod_bit/mod_bit_roof_identification.md)
- [Tar and gravel/BUR](roof_reference_library/tar_and_gravel/tar_and_gravel_roof_identification.md)

Damage-identification guides and images are not positive roof-type references and must not be loaded by the roof-type reference workflow.
