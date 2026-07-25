---
status: implemented
---

# Roof Reference Integration Plan

## Implementation Status

Implemented behind an opt-in feature flag. The legacy one-call AI workflow remains the default when the flag is off.

Enable it for the PCS report worker through `.env` or the process environment:

```text
ROOF_REFERENCE_CLASSIFICATION=1
```

Every image listed under a selected roof type's `reference_images` is supplied
to Stage 2 by default. There is no separate active-image list, so adding an
approved positive example automatically makes it part of future comparisons.
`ROOF_REFERENCE_IMAGES_PER_TYPE` is an explicit emergency cost/size override:
set it to a positive integer to cap each type, or leave it unset/use `all` to
retain complete reference coverage. The report trace records approved and used
counts so incomplete coverage is visible.

When enabled, a roof-reference failure automatically retries the legacy provider call. Static fallback output is used only when provider analysis also fails and `--allow-ai-fallback` is enabled.

## Documentation Structure

Use a hybrid structure:

- `roof_type_classification.md` is the central classification framework and index.
- Each roof-type folder contains its detailed `<roof_type>_roof_identification.md` guide.
- Each identification guide contains material-specific characteristics, visual cues, look-alikes, confidence guidance, mixed-roof considerations, and annotated links to its positive reference images.
- Damage-identification images and guides remain separate from positive roof-type identification references.

## Runtime Integration

Markdown links do not automatically provide local documents or images to an AI API. The report generator must explicitly read each selected guide and encode each selected reference image in the model request.

### Stage 1: Candidate Classification

Provide the model with:

- The target building aerial image
- The central `roof_type_classification.md` guidance
- A concise cross-material comparison or condensed guidance for all supported roof types

Require the model to:

- Segment buildings containing multiple roof zones
- Return the most likely roof-system candidates for each zone
- Preserve ambiguous classifications instead of forcing one material
- Identify the roof-specific guides needed for final comparison

### Stage 2: Reference Comparison

For the leading candidates from Stage 1, provide the model with:

- The target building aerial image
- The complete identification guide for each selected roof type
- Every approved positive reference image for each selected roof type

Require the model to return the final zone-level classification, confidence, supporting cues, remaining alternatives, and image limitations.

## Reference Manifest

Create a central, explicit manifest that maps each supported roof type to:

- Canonical classification name
- Identification-guide path
- Positive identification-image paths
- Optional aliases
- Enabled or disabled status

Do not rely only on automatic folder discovery. An explicit manifest prevents damage examples, temporary files, misspelled filenames, or unrelated images from being sent as positive identification references.
At startup, each active identification guide's positive image links must match
its manifest `reference_images` entries one-for-one. A partial future addition
therefore stops with a configuration error instead of being silently omitted.

## Provider Support

Implement the same reference-loading behavior for both supported providers:

- OpenAI: send guide text as `input_text` and each image as `input_image`.
- Gemini: send guide text as a text part and each image using `inlineData`.

Use the same manifest and candidate-selection rules for both providers.

## Request Controls

- Use every manifest-approved reference image by default; any runtime cap must
  be an explicit, traceable override.
- Label every reference image with its roof type and filename in the request.
- Keep positive identification examples separate from damage examples.
- Validate that every configured guide and image exists before starting an AI request.
- Fail clearly or issue an explicit warning when required references are missing.
- Manage prompt size, image count, latency, and API cost as the library grows.

## Analysis Traceability

Store the following with each generated analysis:

- Classification stage and workflow version
- Model and provider
- Guides supplied to the model
- Reference-image filenames supplied
- Manifest version or hash
- Guide and image hashes or modification timestamps
- Candidate types returned by Stage 1
- Final zone classifications and confidence returned by Stage 2

This makes it possible to reproduce results and determine which reference-library version influenced a report.

## Codex Library Ingestion

Repository-level instructions in `AGENTS.md` define roof-reference additions as
a complete ingestion task. A future Codex session must place the image in the
canonical roof-type folder, update the active identification guide and manifest,
increment the workflow version, update a condition guide when applicable, and
run:

```text
python3 scripts/validate_roof_reference_library.py
python3 -m unittest tests.test_roof_reference_workflow
```

The validator enforces guide/manifest parity, substantive image descriptions,
unique positive image content, valid paths, and complete runtime registration.

## Verification Tests

Add automated tests confirming that:

- The central classification guide is included in Stage 1.
- Candidate-specific guides are included in Stage 2.
- Every selected reference image becomes an actual image input, not merely a Markdown path.
- Only manifest-approved identification images are supplied.
- Missing files produce a clear error or warning.
- Mixed-roof zones remain separate in the structured output.
- OpenAI and Gemini receive equivalent guidance and reference sets.
- Analysis metadata records the references actually supplied.

## Completion Criteria

The integration is complete when the report generator explicitly loads the classification documents and positive reference images, sends only relevant references to each model call, produces zone-level classifications for mixed roofs, and records enough metadata to verify exactly what the AI received.
