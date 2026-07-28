---
status: active
---

# Roof Type Classification

## Purpose

This document is the central decision framework for AI roof-type classification. When the roof-reference feature is enabled, Stage 1 uses this guide to divide a building into visible roof zones and select candidate roof systems. Stage 2 uses the detailed guides and positive images listed in the roof-reference manifest to make the final comparison.

Roof type and roof condition are separate decisions. Do not classify a material from damage, staining, age, or assumed building use alone.

## Supported Candidate Keys

- `tpo` — thermoplastic polyolefin single-ply membrane
- `tpo_pvc_or_coating` — controlled final-stage result for a smooth white single-ply or coated surface whose chemistry cannot be resolved
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
- `mod_bit_coating_or_tar_and_gravel` — controlled final-stage ambiguity when a tan weathered low-slope roof cannot be separated among modified bitumen, a coated roof, and tar-and-gravel/BUR
- `mod_bit_or_tar_and_gravel` — controlled final-stage ambiguity when an asphaltic or aggregate-looking roof cannot be separated between modified bitumen and tar-and-gravel/BUR
- `ballasted_or_tar_and_gravel` — controlled final-stage ambiguity when a tan aggregate-covered roof cannot be separated between a ballasted membrane and tar-and-gravel/BUR
- `unknown` — evidence is insufficient to establish a material family

## Classification Workflow

1. Confirm the visible surface is part of the target building roof.
2. Divide the roof into contiguous zones using parapets, ridges, expansion joints, elevation changes, additions, and material transitions supported by non-color construction evidence. Do not create a separate material zone from color variation alone when the field, seams, edges, slope, and elevation remain continuous.
   Do not create roof-material zones for parapet coping, edge trim, curbs, equipment housings, mechanical screens, or other rooftop components that are not roof fields.
3. Before naming a material, record the zone's color family, seam pattern, surface texture, perimeter-stone transition, and raised-ridge pattern. Use `uncertain` when the image does not resolve a cue; do not convert an unresolved cue into an observed absence.
4. Apply the fundamental material priors below to those observations, then return as many as three evidence-supported candidates per zone. Do not include unsupported possibilities merely because they are common.
5. Stage 1 returns the supported specific candidates. In the Stage 2 final output, use `tpo_pvc_or_coating` for an unresolved white membrane or reflective roof that cannot be separated among TPO, PVC, and coating, and preserve the specific materials as alternatives.
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
| Metal | Repeated straight raised ribs, rigid planes, visible slope/drainage direction, directional sheen, crisp ridges and edge trim | Membrane attachment rows may resemble ribs at poor resolution |
| Modified bitumen | Dark or granular field, low-profile narrow roll laps, staggered end joints, flexible sheet character | Can resemble EPDM, smooth BUR, coated asphalt roofing, or weathered metal when rib height is missed |
| Tar and gravel/BUR | Fine embedded-looking aggregate, uniform field, no exposed sheet-lap grid | Can be indistinguishable from a loose-ballasted membrane roof |
| Coating | Roller or spray variation, old seams and repairs showing through, one finish spanning different substrates | New coating can resemble a new single-ply membrane |

## Fundamental Material Priors

Use these as ordered starting probabilities, not absolute rules. Geometry, texture, seams, edge construction, and image quality can strengthen or override color.

- **White:** begin with the white single-ply/coating family. Select TPO only when visible seams, flashings, or other TPO-specific evidence supports it. If a smooth white roof remains visually unresolved among TPO, PVC, and coating, use `tpo_pvc_or_coating` at reduced confidence in the Stage 2 final output.
- **Light monolithic asphaltic or coated fields:** light color alone does not establish the white single-ply family. When image quality is sufficient to expose a continuous roof field but no broad repeated sheet-seam layout, welded details, or membrane flashing construction is visible, and the surface instead appears muted, monolithic, weathered, or coating-like, compare modified bitumen and coating before TPO/PVC. Use `mod_bit_or_coating` when roll laps and coating-application evidence remain unresolved. This rule does not turn blurred or obstructed seams into an observed absence.
- **Gray:** first compare weathered TPO with modified bitumen. Broad, regular sheet seams on a smooth field favor weathered TPO. A gray asphaltic or granular field without a resolved membrane-sheet layout favors modified bitumen. If the image is too soft to reveal seams, mark the seam pattern `uncertain`; do not treat it as proof that seams are absent.
- **Black:** strongly favor EPDM when the field is smooth, matte, and membrane-like. Frequent narrow roll laps, granules, or asphaltic texture favor modified bitumen instead. Use `epdm_or_mod_bit` when those distinguishing details are unresolved.
- **Field color before bright details:** determine color from the exposed roof field, not from seam tape, repair bands, curbs, rooftop equipment, glare, or compression highlights. A dark charcoal membrane does not become a white single-ply roof because localized linear or rectangular details appear white. Use the white single-ply family only when the roof field itself is predominantly white, cream, or very light gray.
- **Tan aggregate:** compare ballasted with tar-and-gravel/BUR. A deliberate perimeter band with distinctly larger or differently colored stone strongly favors ballasted. A more uniform fine embedded-looking aggregate field favors tar-and-gravel/BUR. When the perimeter transition, stone size, or embedment is not apparent at the available resolution, use `ballasted_or_tar_and_gravel` rather than forcing either type.
- **Metal hard gate:** classify a zone as `metal` only when the target image shows both (1) dense, narrow, uniformly repeated manufactured raised ribs and (2) rigid pitched geometry, normally a visible peak or raised ridge with the ribs running perpendicular downslope. A high similarity score to a metal reference, white color, a rectangular footprint, broad sheet seams, or attachment rows cannot substitute for either required finding.
- **Long parallel raised ridges:** raised ribs support metal only when they run consistently downslope across rigid pitched planes and tie into visible ridge or high-point construction. Low-profile membrane seams without that rigid geometry do not establish metal.
- **Bright white ribbed roofs:** do not let a reflective white finish override manufactured geometry. Dense fine straight ribs that remain uniformly spaced and continuous across the full rigid field strongly favor metal even when the roof is white or coated. TPO/PVC sheets normally produce broader low-profile lap layouts rather than a dense full-field rib profile.
- **Metal versus modified bitumen:** dense straight lines that remain uniformly spaced and continuous across broad rigid roof planes, align with a visible slope or drainage direction, and continue through weathered or repaired areas strongly favor metal. Modified-bitumen roll laps are low-profile sheet seams; they may form narrow parallel bands, but they do not normally create a full-field raised-rib profile across multiple sloped planes. Do not let gray color, coating wear, patching, or surface discoloration override manufactured rib and slope geometry.
- **Center ridge and panel-bay repairs:** a continuous raised ridge dividing two shallow roof planes, with numerous narrow ribs terminating perpendicular to that ridge on both sides, strongly favors metal even when overhead imagery makes the pitch look nearly flat. Contrasting rectangular repairs that occupy uniform panel-bay widths and align precisely with the rib grid support replaced metal panel sections. Modified-bitumen or coating patches may be rectangular, but they do not create or preserve a rigid center-ridge-and-perpendicular-rib assembly.
- **Metal drainage-edge context:** clearly resolved exposed eaves or rakes, crisp shedding-edge trim, gutters, or downspouts can reinforce metal when they agree with a center ridge, opposing pitched planes, and ribs running downslope to those edges. Do not classify from apparent parapet absence alone, because low walls may be hidden in overhead imagery and membrane roofs can also use exposed drainage edges. Keep parapet presence or absence out of customer-facing roof-system conclusions.
- **Weathering streaks are not metal ribs:** irregular linear wear, chalking, coating loss, repair marks, and runoff streaks may be dense but vary in width, spacing, continuity, or direction. Without coherent raised shadows, rigid panel planes, visible slope alignment, or metal edge/ridge construction, treat those marks as condition evidence rather than metal geometry. A heavily weathered asphaltic-looking field with unresolved roll laps or coating details should use `mod_bit_or_coating`, not `metal`.
- **Two-tone metal remains one material when construction geometry continues:** a sharp color transition across a pitched roof does not create a second material zone when the peak ridge, opposing planes, perpendicular rib direction, rib spacing, and rigid metal-panel construction continue through both tones. The difference may reflect installation date, panel replacement, coating age, finish, or weathering; state that cause as unresolved unless records or closer evidence establish it.
- **Flat membrane banding versus metal:** when one continuous flexible-looking flat field has broad low-profile sheet seams or roll/lap banding but lacks the required narrow raised ribs and pitched/ridged rigid geometry, exclude metal. For a smooth white field, use the white single-ply/coating family; for an asphaltic field, compare modified bitumen and coating. Do not split one continuous membrane into several metal zones from broad bands.
- **Repair patches on aged dark asphaltic fields:** small localized gray or black rectangles with discrete overlap edges, contrasting tone, or interruption of the underlying roll pattern may be applied membrane patches. Require local repair context; do not call every rectangle a patch because curbs, equipment, shadows, and imagery artifacts can also be rectangular.

## Required Ambiguity Rules

- Use `tpo_pvc_or_coating`, displayed as **White Single-Ply or Coated Roof**, when a white or light-colored membrane-like roof cannot be reliably separated among TPO, PVC, and coating from the available imagery. Keep confidence at 60 or below and retain `tpo`, `pvc`, and `coating` as alternatives when supported.
- Do not return standalone `pvc` or `coating` as a final aerial classification. Use `pvc_or_coating`, displayed as **PVC or Coated Roof**, whenever the imagery favors that family over TPO but cannot prove whether the exposed surface is PVC membrane or a coating.
- Close visual details, readable markings, specifications, or other non-aerial records may support exact PVC or coating identification during a separate verification workflow, but the standard aerial report must retain the combined result.
- A highly weathered coating may appear patchy, chalky, tan, gray, or uneven rather than uniformly white. Favor `pvc_or_coating` over TPO when a monolithic finish shows irregular application variation, old repairs or substrate details telegraphing through, and localized wear-through without a consistent membrane-sheet layout.
- Apply `tpo` only to a genuinely smooth, membrane-like white or light roof with resolved TPO-supporting details. Do not apply it to an unresolved white surface or to a patchy, heavily weathered, asphaltic-looking, or aggregate-textured surface merely because sun exposure makes portions appear light.
- Use `epdm_or_mod_bit`, displayed as **EPDM or Modified Bitumen**, when a dark membrane is established but width, seams, and texture do not support choosing between those two systems.
- Use `mod_bit_or_coating`, displayed as **Modified Bitumen or Coated Roof**, when a weathered asphaltic-looking surface is established but coating-specific evidence and roll-lap details remain unresolved.
- Also use `mod_bit_or_coating` for an adequately visible light or off-white monolithic roof field that lacks a broad manufactured single-ply sheet layout and has no TPO/PVC-specific welded or flashing details, when smooth modified bitumen and a coating remain the supported alternatives. Do not select the white single-ply family from brightness and smoothness alone.
- Use `mod_bit_coating_or_tar_and_gravel`, displayed as **Modified Bitumen, Coated Roof, or Tar and Gravel**, when a tan weathered low-slope field supports all three possibilities but aerial resolution does not resolve roll laps, coating application evidence, or embedded aggregate well enough to eliminate any of them. Tan color is only a supporting cue and never proves tar-and-gravel by itself.
- Use `mod_bit_or_tar_and_gravel`, displayed as **Modified Bitumen or Tar and Gravel**, when the image suggests an asphaltic or aggregate surface but cannot resolve roll laps, stone embedment, or loose ballast well enough to choose one.
- Use `ballasted_or_tar_and_gravel`, displayed as **Ballasted or Tar and Gravel**, when a tan aggregate-covered roof is established but the stone-size/color transition at the edge, stone embedment, and underlying assembly cannot be resolved well enough to choose ballasted or BUR.
- Use `unknown/indeterminate roof type` rather than forcing a candidate from color alone.
- Return the canonical type `metal` whenever metal is supported. Describe a subtype such as standing seam, ribbed, or corrugated only in supporting observations, and only when the profile is clearly resolved.
- Do not classify a dark low-slope zone as metal from faint parallel lines or apparent panel divisions alone. Require clear rigid planes, repeated raised ribs with consistent shadows, or metal edge/ridge detailing. If those cues are unresolved and the surface is plausibly a dark membrane, prefer `epdm`, `mod_bit`, or `epdm_or_mod_bit` with metal retained only as an alternative.
- Soft overhead imagery does not create an exception to the metal hard gate. If rib height, narrow repeated rib spacing, pitch, or ridge relationship is unresolved, retain metal only as an alternative and classify the supported membrane/coating family instead.
- When a light gray or weathered roof has dense straight full-field ribs plus visible roof-plane slope, compare metal directly against modified bitumen and favor metal unless the lines resolve as low-profile sheet laps. Weathering, repairs, or coating loss are condition findings and must not be used to relabel a visibly ribbed metal substrate as modified bitumen.
- A dark, flat, matte attached field with broad membrane character and no resolved raised-rib shadows or metal edge construction favors EPDM over metal, even when faint straight lines are present.
- On a dark charcoal low-slope field, broad low-profile rectangular sheet seams favor EPDM. Narrower and more frequent roll laps, staggered end joints, mineral granules, or an asphaltic texture favor modified bitumen. When the secondary zone is visibly separate but these details are unresolved, preserve it as `epdm_or_mod_bit`; do not relabel it white single-ply from bright seams or patches.

## Mixed-Roof Requirements

- Do not collapse visibly different zones into one whole-building material.
- Do not split one continuous roof section into multiple material zones merely because it contains white, cream, tan, gray, or dark patches. When seam geometry, perimeter construction, elevation, slope, and surface character continue through the variation, keep one material zone and treat the color differences as condition evidence.
- Common causes of within-zone color variation include UV aging, chalking, accumulated dirt, weathering, prior repairs, moisture retention, and drainage or ponding patterns. Identify ponding only when supporting evidence such as retained water, basin-shaped staining, sediment rings, algae-like growth, or drainage concentration is visible; color variation alone does not prove ponding, leakage, or wet insulation.
- Do not set suspected ponding from general deterioration, streaking, or mottled discoloration. The flag requires affirmative visible evidence such as standing or retained water, a basin-shaped wet pattern, a sediment/tide ring, algae-like concentration, or a blocked-drain pattern. An explicit absence of those cues means suspected ponding is false.
- **All metal roofs:** do not report ponding as an observation or visible-risk factor. Set `suspected_ponding` to false and remove ponding, standing-water, and retained-water wording from customer-facing observations and notes whenever every material zone is metal. Metal panel roofs are treated as shedding water by design. Report a separately visible gutter, drain, deformation, or structural concern by its physical name without labeling it ponding.
- On a predominantly gray-black aged membrane, irregular soft-edged tan areas that follow a low-area or basin pattern can support recurring moisture retention or ponding when they differ from straight-edged repair patches and material boundaries. Combine this with drainage context; tan color alone is insufficient.
- Widespread weathering plus repeated repair patches and affirmative ponding evidence may support a **probable end-of-service-life** assessment and elevated leakage risk. Do not claim an active leak, wet insulation, or a precise remaining life without onsite inspection and moisture testing.
- Widespread weathering can obscure seams, flashings, texture, and original color. Reduce material confidence when those distinguishing cues are degraded. For an aged light roof that remains within the white membrane/coating family but cannot be separated among TPO, PVC, and coating, use `tpo_pvc_or_coating` for the single continuous zone.
- Give every zone a stable identifier, location description, confidence, supporting cues, alternatives, limitations, and approximate visible-area percentage.
- The whole-building classification must be `mixed` when more than one materially different roof system is visible.
- Small metal canopies, membrane additions, rooftop penthouses, and paver terraces should remain separate when their construction differs from the main roof.
- Localized patches concentrated around metal-roof penetrations, curbs, seams, or fasteners indicate prior repair activity and elevated flashing/seal leakage risk. They do not establish an active leak by themselves. Keep the substrate classified as metal when the manufactured ribs remain visible through the repaired or coated field.
- A continuous metal field with visible penetration repairs can be described as a potential silicone-restoration candidate when no aerial evidence establishes conditions beyond restoration. Always make the recommendation conditional on onsite inspection, moisture and adhesion testing, dry/sound panels and insulation, substrate compatibility, required repairs and preparation, drainage review, and manufacturer warranty eligibility.
- **Fiberglass skylight panels on metal roofs:** repeated narrow rectangular panels with consistent dimensions, orientation, spacing, and alignment within the metal rib grid may be translucent fiberglass skylights. Their organized repetition and integration with the panel layout distinguish them from random patches, coating loss, staining, and shadows. Record skylights as present when these cues are supported. Never include their light-transmitting faces in a silicone coating scope; require masking, protection, perimeter-detail inspection, and a clearly marked exclusion so the panels remain translucent and identifiable.
- Do not let a dominant roof type absorb a smaller attached section. A small zone with different color, texture, seam frequency, or boundary geometry must be evaluated separately, including narrow modified-bitumen sections beside a larger TPO roof.
- When the main roof is confirmed EPDM and an attached dark or gray membrane section cannot be separated between EPDM and modified bitumen, report two zones: `epdm` for the confirmed main field and `epdm_or_mod_bit` for the unresolved attached field.
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
