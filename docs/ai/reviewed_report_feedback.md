---
status: active
---

# Reviewed Report Feedback Workflow

## Purpose

Manual report corrections can improve future processing only through an explicit, reviewed workflow. Editing a report still creates an immutable revision. The editor may separately opt in by selecting **Submit this correction for review to improve future roof reports**.

## Lifecycle

1. **Pending review:** preserve the original value, corrected value, editor comment, property identity, imagery identity, source revision, and corrected revision. The correction does not affect any other report.
2. **Approved:** a qualified reviewer confirms that the correction is supported and identifies its appropriate scope. Approval alone does not change runtime processing.
3. **Applied:** Codex or an authorized maintainer adds durable artifacts appropriate to the correction, validates them, and records the resulting workflow version and artifact paths. Only this state may affect future reports.
4. **Rejected:** preserve the record for audit history, but never use it in prompts, rules, references, matching, or evaluation.

## Application Requirements

- Roof-material corrections require the source image, reviewer-supported canonical type or controlled ambiguity, guide changes, manifest registration when the image is a valid positive reference, known-building identity when available, and an evaluation case.
- Mixed-roof corrections require confirmed zone locations, approximate visible-area shares, alternatives, and limitations.
- Condition corrections update the applicable condition guide and scoring guidance. They must not become positive material references unless the material is independently confirmed.
- Roof-configuration corrections update the relevant prompt or structural rule and receive a regression test.
- Narrative-only corrections update customer-facing writing rules and receive a regression test; the edited prose is not copied blindly into unrelated reports.
- Square-footage corrections may use the existing explicit property override. They do not become global estimation rules merely because they were submitted as feedback.

## Safety Rules

- Never train from every comment automatically.
- Never apply pending, rejected, or merely approved feedback to report generation.
- Never broaden a property-specific correction into a global rule without evidence that it generalizes.
- Do not place customer or reviewer process commentary in customer-facing report narratives.
- An applied record must name the workflow version and every guide, manifest, reference, matching, or evaluation artifact that carries the correction.

## Local Queue Commands

```text
python3 scripts/manage_roof_processing_feedback.py list <queue-directory> --status pending_review
python3 scripts/manage_roof_processing_feedback.py review <record.json> --approve --reviewed-by <name> --note <reason>
python3 scripts/manage_roof_processing_feedback.py apply <record.json> --workflow-version <version> --artifact <path> --applied-by <name>
```

The Supabase contract mirrors the same pending, approved, rejected, and applied states. Review and application functions remain service-role-only.
