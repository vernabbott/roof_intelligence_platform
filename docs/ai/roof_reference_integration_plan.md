---
status: implemented
---

# Roof Reference Integration Plan

## Implementation Status

Implemented behind an opt-in feature flag. The legacy one-call AI workflow remains the default when the flag is off.
When enabled, the roof-reference workflow uses one reference-assisted provider
call per roof. Reference families and images are selected locally before the
request. The provider returns zone evidence, ranked material candidates,
confidence, limitations, and the complete report in the same response. An
uncertain result uses controlled ambiguity wording and is marked for human or
onsite confirmation; it does not trigger another provider call.

Enable it for the PCS report worker through `.env` or the process environment:

```text
ROOF_REFERENCE_CLASSIFICATION=1
```

Every image listed under a selected roof type's `reference_images` is eligible
for deterministic retrieval. Images are normalized to a common square canvas,
ranked against the target, and a balanced top-reference bundle is supplied to
the single analysis call. The default limits are eight total images and two per roof type.
`ROOF_REFERENCE_MAX_RETRIEVED_IMAGES` and
`ROOF_REFERENCE_IMAGES_PER_TYPE` can override those limits. The report trace
records approved sources, normalized inputs, similarity scores, and used
counts.

The former second-call metal-versus-membrane resolver is retired in the
single-call workflow. Metal and modified-bitumen references are reserved in the
locally selected comparison set, allowing the primary request to evaluate the
known confusion pair without another billable call. Setting
`ROOF_METAL_MEMBRANE_RESOLVER=1` no longer creates an additional request; the
trace records that the resolver was retired by the single-call workflow.

Before reference selection, the workflow checks reviewer-confirmed
known-building metadata. An exact parcel number + imagery source + imagery date
match locks the canonical roof material while the same single call assesses
condition and other visible characteristics.

When enabled, a roof-reference failure automatically retries the legacy provider call. Static fallback output is used only when provider analysis also fails and `--allow-ai-fallback` is enabled.

## Documentation Structure

Use a hybrid structure:

- `roof_type_classification.md` is the central classification framework and index.
- Each roof-type folder contains its detailed `<roof_type>_roof_identification.md` guide.
- Each identification guide contains material-specific characteristics, visual cues, look-alikes, confidence guidance, mixed-roof considerations, and annotated links to its positive reference images.
- Damage-identification images and guides remain separate from positive roof-type identification references.

## Runtime Integration

Markdown links do not automatically provide local documents or images to an AI API. The report generator must explicitly read each selected guide and encode each selected reference image in the model request.

### Local Reference Selection

Without making a provider call:

- Normalize the target image.
- Rank approved reference images against the target.
- Select the most similar distinct roof families.
- Reserve metal and modified-bitumen examples for the known confusion pair.
- Prefer an exact reviewer-confirmed building match when parcel, source, and image date agree.

### Single Reference-Assisted Analysis

Provide the model with the target image, central guide, selected identification
guides, and selected reviewer-confirmed reference images. Require one response
that:

- Segment buildings containing multiple roof zones
- Return the most likely roof-system candidates for each zone
- Preserve ambiguous classifications instead of forcing one material
- Return the complete condition assessment and report content
- Cap confidence when distinguishing construction details are unresolved
- Avoid a follow-up model request; low-confidence output is routed to human or onsite confirmation

## Reference Manifest

Create a central, explicit manifest that maps each supported roof type to:

- Canonical classification name
- Identification-guide path
- Positive identification-image paths
- Optional crop, visible-cue, condition-tag, and known-building metadata
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

- Consider every manifest-approved reference image during deterministic
  retrieval and send the configured top-reference subset.
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
- Candidate types and visual evidence returned by the single analysis call
- Final zone classifications, confidence, review recommendation, and uncertainty reasons

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
python3 scripts/evaluate_roof_reference_library.py
```

The validator enforces guide/manifest parity, substantive image descriptions,
unique positive image content, valid paths, and complete runtime registration.
Corrected production examples are also registered as offline evaluation cases,
so exact matching and retrieval quality are checked without paid API calls.

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
