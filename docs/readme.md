---
status: draft
---

# Roof Intelligence Documentation

## Current Status

The following operational documents are active:

- `ai/cost_estimation.md` drives cost-estimation configuration.
- `ai/report_summary.md` drives report-summary and recommendation configuration.
- `ai/roof_information.md` drives Roof Information card material wording and primary/secondary display rules.
- `ai/roof_type_classification.md` and the seven `*_roof_identification.md` guides drive the feature-flagged two-stage roof-reference workflow.

The roof-reference documents are loaded only when `--roof-reference-classification` or `ROOF_REFERENCE_CLASSIFICATION=1` is used with AI analysis. Damage-identification guides remain separate and are not loaded as positive roof-type examples. Other draft documents remain disconnected from runtime processing.

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
- [Report summary](ai/report_summary.md)
- [Roof information](ai/roof_information.md)
- [Recommendation engine](ai/recommendation_engine.md)

### Business Rules

- [Business rules](ai/business_rules/business_rules.md)
- [Opportunity rules](ai/business_rules/opportunity_rules.md)
- [Overlay rules](ai/business_rules/overlay_rules.md)
- [Replacement rules](ai/business_rules/replacement_rules.md)

### Roof Reference Guides

- Ballasted: [identification](ai/roof_reference_library/ballasted/ballasted_roof_identification.md), [damage](ai/roof_reference_library/ballasted/ballasted_roof_damage.md)
- EPDM: [identification](ai/roof_reference_library/epdm/epdm_roof_identification.md), [damage](ai/roof_reference_library/epdm/epdm_roof_damage.md)
- Metal: [identification](ai/roof_reference_library/metal/metal_roof_identification.md), [damage](ai/roof_reference_library/metal/metal_roof_damage.md)
- Modified bitumen: [identification](ai/roof_reference_library/mod_bit/mod_bit_roof_identification.md), [damage](ai/roof_reference_library/mod_bit/mod_bit_roof_damage.md)
- PVC: [identification](ai/roof_reference_library/pvc/pvc_roof_identification.md), [damage](ai/roof_reference_library/pvc/pvc_roof_damage.md)
- Tar and gravel: [identification](ai/roof_reference_library/tar_and_gravel/tar_and_gravel_roof_identification.md), [damage](ai/roof_reference_library/tar_and_gravel/tar_and_gravel_roof_damage.md)
- TPO: [identification](ai/roof_reference_library/tpo/tpo_roof_identification.md), [damage](ai/roof_reference_library/tpo/tpo_roof_damage.md)
- [Operational reference manifest](ai/roof_reference_manifest.yaml)
- [Integration design and operating instructions](ai/roof_reference_integration_plan.md)

## Roof-Type Readiness

| Roof type | Identification status | Processing status | Approval notes |
|---|---|---|---|
| Ballasted | Active | Feature flagged | Manifest-approved positive samples only |
| EPDM | Active | Feature flagged | Manifest-approved positive samples only |
| Metal | Active | Feature flagged | Manifest-approved positive samples only |
| Modified bitumen | Active | Feature flagged | Manifest-approved positive samples only |
| PVC | Active | Feature flagged | Manifest-approved positive samples only |
| Tar and gravel | Active | Feature flagged | Manifest-approved positive samples only |
| TPO | Active | Feature flagged | Manifest-approved positive samples only |

## Maintenance Notes

- Use lowercase snake_case for directory and file names.
- Store roof-type example images inside that roof type's `images/` directory.
- Keep image references relative to the Markdown guide.
- Preserve one identification guide and one separate damage guide for each roof type.
- Keep draft documentation disconnected from runtime processing until approved.
