# PilotPoint IQ Roof Reference Workflow

When the user asks Codex to add, save, register, or teach the system a roof
reference image, treat the request as a complete library-ingestion task.

## Required inputs

Obtain or infer from the user's request:

- The source image.
- The reviewer-confirmed canonical roof type.
- A factual description of the visible identification cues.
- Any separately confirmed condition or damage category.
- When the example is tied to a known report: parcel number, aerial imagery
  source, and aerial image date.
- A normalized crop box when the source image contains masks, labels, adjacent
  buildings, or substantial non-roof context.

Ask only when the roof type or intended image is genuinely ambiguous. Never
infer a reviewer-confirmed roof type from the image alone.

## Positive roof-type reference

For a confirmed positive identification example:

1. Inspect the image before editing files.
2. Copy it into
   `docs/ai/roof_reference_library/<roof_type>/images/` with a unique,
   descriptive, lowercase filename. Preserve the original image data and file
   extension unless conversion is necessary.
3. Add a titled example, Markdown image link, and substantive visible-cue
   description to that roof type's active identification guide.
4. Add the same project-relative image path to the roof type's
   `reference_images` list in `docs/ai/roof_reference_manifest.yaml`. Prefer
   the structured form with `path`, reviewer-confirmed visible `cues`,
   `condition_tags`, and normalized `crop_box`. If the report identity is
   known, also register `known_buildings` using the exact parcel number,
   imagery source, and image date, and set `reviewer_confirmed: true`.
5. Increment `workflow_version` in the manifest.
6. Do not create or restore a `stage2_images` list. Runtime Stage 2
   uses deterministic top-reference retrieval from all approved
   `reference_images` entries.
7. If the user also confirmed a condition or damage category, add the same
   image and an appropriately limited description to the relevant damage
   guide. Damage-guide registration does not replace identification-guide and
   manifest registration.
8. For a corrected production misclassification, add or update a case in
   `docs/ai/roof_reference_eval_cases.yaml` and ensure the target image is
   tracked. Evaluation cases must name the expected canonical roof type and,
   when known, the expected top reference and property identity.

## Condition-only example

If the user confirms only a condition or damage category, update the
appropriate damage guide but do not add the image to the positive
`reference_images` manifest until the roof type is reviewer-confirmed.

## Required validation

Run both commands after every roof-reference change:

```text
python3 scripts/validate_roof_reference_library.py
python3 -m unittest tests.test_roof_reference_workflow
python3 scripts/evaluate_roof_reference_library.py
```

The task is incomplete if validation fails. Fix missing guide links, manifest
entries, descriptions, duplicate registrations, or tests before reporting
completion. In the final response, state the canonical roof type, image path,
guides updated, manifest workflow version, evaluation result, and validation
result.
