---
status: active
---

# Report Summary

## Purpose

This document is the operational source for report-summary and recommendation wording. The report generator validates and loads the labeled YAML block below at startup. Condition scoring and aerial-image age calculations remain in Python; the narrative guidance, fallback text, visible-risk language, and condition-alignment terms come from this document.

After changing this configuration, restart any long-running report process before generating another report.

## Runtime Configuration

```yaml report_summary
schema_version: 1

limits:
  summary_max_characters: 475
  recommendation_max_characters: 950

ai_guidance: >-
  Write a concise report summary and recommendation using only visible aerial-image evidence and supplied property metadata. Keep the summary broad, identify the final apparent condition and risk, and avoid overstating exact membrane chemistry from aerial imagery alone. Include visibly supported staining, discoloration, suspected ponding, drainage concerns, wet-insulation or leak potential, penetrations, flashing risks, tree overhang, and debris. Reference the supplied formatted aerial-photo date when available, acknowledge that older imagery may understate current deterioration, and do not apply an imagery-age numerical penalty because the reporting system performs that adjustment. Do not include underwriting snapshots or carrier appetite. For an apparently restorable low-slope roof that is not asphalt shingle, recommend evaluating silicone roof restoration before a more costly overlay or replacement. Explain conditionally that a qualifying silicone system may reduce tear-off waste, cost, and disruption; create a seamless monolithic white reflective cool-roof surface; withstand ponding water when properly designed and installed; improve resistance to UV exposure and hail; and qualify for a manufacturer warranty of up to 20 years. Do not claim that coating creates no waste, causes no disruption, suits every roof, or guarantees hail coverage. Always direct the user to a qualified commercial roof-coating contractor for an onsite inspection, moisture testing when warranted, confirmation of system and warranty eligibility, required repairs and preparation, and a reliable project-price proposal. If visible evidence or supplied information indicates widespread moisture, failed insulation, structural or deck deterioration, an incompatible substrate, asphalt shingles, or a roof beyond restoration, recommend an appropriate overlay or replacement evaluation instead. Keep both fields within their configured character limits.

fallback:
  summary: >-
    This preliminary report uses available property records, building measurements, and aerial-image information to establish a planning baseline for the roof. The roof assembly, moisture condition, remaining service life, and required repairs cannot be confirmed without an onsite inspection. Cost estimates are provided for preliminary comparison and budgeting.
  recommendation: >-
    Before selecting a roof replacement or overlay, engage a qualified commercial roof-coating contractor to perform an onsite inspection and evaluate whether silicone restoration is appropriate. The contractor should conduct moisture testing when warranted, confirm membrane compatibility and warranty eligibility, identify required repairs and preparation, and provide a reliable project-price proposal. If the roof is dry, structurally sound, well-adhered, and repairable, silicone restoration may provide a lower-cost, less disruptive alternative to replacement or overlay. If the roof is not suitable for restoration, obtain an appropriate overlay or replacement proposal based on the field findings.

visual_risk:
  concern_template: "Visible risk factors include {labels}."
  contractor_addendum: >-
    A qualified commercial roof-coating contractor should perform an onsite inspection, complete moisture testing when warranted, verify drainage, moisture, penetrations, flashing, and debris-related damage, confirm silicone-system and warranty eligibility, and provide a reliable project-price proposal.
  factors:
    dark_staining_or_discoloration:
      label: dark staining or inconsistent roof color
      indicators:
        - dark stain
        - darkened
        - discolor
        - uneven color
        - staining
        - mottled
    suspected_ponding:
      label: possible ponding or drainage stress
      indicators:
        - ponding
        - standing water
        - poor drainage
        - water retention
    high_penetration_density:
      label: high penetration or rooftop-unit density
      indicators:
        - many penetration
        - numerous penetration
        - skylight
        - vent
        - rooftop unit
        - rtu
        - curb
    overhanging_trees_or_debris:
      label: tree overhang or roof debris exposure
      indicators:
        - overhanging tree
        - tree overhang
        - debris
        - leaf
        - branches

condition_alignment:
  condition_terms:
    - good
    - fair
    - poor
  risk_terms:
    - low
    - moderate
    - medium
    - high
  adjusted_condition_template: "in {condition} current-likely condition"
```

## Report Summary Card

The card contains the summary narrative followed by a bold `Recommendation:` label and the recommendation narrative. OpenAI returns both values through the report-analysis JSON schema. The program then applies visible-risk and aerial-image age adjustments before rendering the report.

## Silicone Restoration Recommendation

For an apparently eligible low-slope roof, the recommendation should encourage the building owner to evaluate silicone restoration before committing to an overlay or complete replacement. All benefits are conditional on field verification, system compatibility, proper preparation and application, manufacturer requirements, and the selected warranty.

Every silicone-restoration recommendation must direct the user to a qualified commercial roof-coating contractor who will:

- Perform an onsite roof inspection
- Verify the membrane, substrate, deck, drainage, seams, flashing, penetrations, and required repairs
- Perform moisture testing or a moisture survey when warranted
- Confirm adhesion, compatibility, restoration eligibility, and manufacturer-warranty eligibility
- Establish preparation, repair, application-rate, and warranty requirements
- Provide a reliable scope of work and project-price proposal

If field findings identify widespread moisture, failed insulation, structural or deck deterioration, an incompatible substrate, asphalt shingles, or a roof beyond restoration, the contractor should evaluate an appropriate overlay or replacement instead.

## Processing Order

```text
Markdown-configured AI or fallback summary
-> visible-risk scoring and Markdown-configured narrative adjustment
-> aerial-image age scoring and Markdown-configured wording alignment
-> report rendering
```
