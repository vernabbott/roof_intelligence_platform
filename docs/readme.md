---
status: draft
---

# Roof Intelligence Documentation

## Current Status

All Markdown files under `docs/` are drafts. They are reference material under development and are not approved for production processing.

No document in this directory should currently be loaded into AI prompts, condition scoring, business rules, recommendations, cost estimation, or report generation.

## Activation Policy

Documentation will be introduced into processing only after explicit approval by roof type and purpose. Approving one roof type does not approve any other roof type or any shared scoring or business-rule document.

Before activating a document:

- Confirm its technical content is complete and reviewed
- Confirm example images and classifications are accurate
- Confirm severity and confidence definitions are approved
- Confirm image sources and usage rights are documented
- Define the exact processing component that may consume it
- Add tests demonstrating the intended behavior
- Change its status from `draft` only after approval

## Documentation Map

### System Documents

- [System architecture](system_architecture.md)
- [Roof condition AI scoring specification](roof_condition_ai_scoring.md)
- [Codex instructions](codex_instructions.md)

### AI Specifications

- [AI workflow](ai/ai_workflow.md)
- [Roof type classification](ai/roof_type_classification.md)
- [Universal conditions](ai/universal_conditions.md)
- [Confidence scoring](ai/confidence_scoring.md)
- [Roof condition scoring weights](ai/scoring_weights.md)
- [Opportunity scoring](ai/opportunity_scoring.md)
- [Cost estimation](ai/cost_estimation.md)
- [Recommendation engine](ai/recommendation_engine.md)

### Business Rules

- [Business rules](ai/business_rules/business_rules.md)
- [Opportunity rules](ai/business_rules/opportunity_rules.md)
- [Overlay rules](ai/business_rules/overlay_rules.md)
- [Replacement rules](ai/business_rules/replacement_rules.md)

### Roof Reference Guides

- [Ballasted](ai/roof_reference_library/ballasted/ballasted_roof_damage.md)
- [EPDM](ai/roof_reference_library/epdm/epdm_roof_damage.md)
- [Metal](ai/roof_reference_library/metal/metal_roof_damage.md)
- [Modified bitumen](ai/roof_reference_library/mod_bit/mod_bit_roof_damage.md)
- [PVC](ai/roof_reference_library/pvc/pvc_roof_damage.md)
- [Tar and gravel](ai/roof_reference_library/tar_and_gravel/tar_and_gravel_roof_damage.md)
- [TPO](ai/roof_reference_library/tpo/tpo_roof_damage.md)

## Roof-Type Readiness

| Roof type | Document status | Processing status | Approval notes |
|---|---|---|---|
| Ballasted | Draft | Disabled | Pending review |
| EPDM | Draft | Disabled | Pending review |
| Metal | Draft | Disabled | Pending review |
| Modified bitumen | Draft | Disabled | Pending review |
| PVC | Draft | Disabled | Pending review |
| Tar and gravel | Draft | Disabled | Pending review |
| TPO | Draft | Disabled | Pending review |

## Maintenance Notes

- Use lowercase snake_case for directory and file names.
- Store roof-type example images inside that roof type's `images/` directory.
- Keep image references relative to the Markdown guide.
- Preserve a single guide for each roof type unless a specialized document is explicitly needed.
- Keep draft documentation disconnected from runtime processing until approved.
