---
status: active
---

# Roof Reference Pilot Findings

## Purpose

This document records reviewer-confirmed roof types from the initial roof-reference pilot. Use these findings to calibrate the workflow and to evaluate later reruns. They are review labels for the named pilot images, not universal rules based on address or building use.

## Excluded Sample

### 4908402004 — 143 Union Blvd

- Visible roof: asphalt roof outside the current low-slope reference-library scope
- Pilot status: excluded
- Do not rerun or include this property when calculating reference-workflow accuracy.

## Adams County Review Labels

### 0182512101037 — 6345 Colorado Blvd

- Primary type: metal
- Do not assign standing seam, ribbed, corrugated, or another metal subtype because the source image does not resolve the profile clearly enough.
- The aerial image is soft and does not resolve raised ribs or attachment details. Material confidence must therefore remain low to moderate even though the reviewed material family is metal.

### 0172131300018 — 4201 E 72nd Ave

- Primary type: ballasted
- The broad tan aggregate-covered areas are ballast, not coating, PVC, or TPO.
- `ballasted_005.jpg` is a closer positive reference for this roof.

### 0172133301001 — 7200 Quebec Pkwy

- Primary type: TPO
- Secondary type: metal
- Do not add PVC or coating merely because the white membrane chemistry cannot be resolved from the aerial image.

### 0182317107020 — 5101 Quebec St

- Primary type: TPO
- Secondary type: metal
- Preserve the materially distinct metal section as a secondary roof zone.

## Jefferson County Review Labels

### 4917105011 — 12043 W Alameda Pkwy

- Primary type: TPO
- Secondary type: EPDM
- The dark attached roof field is EPDM, not metal.
- Do not force metal from unclear linear features on a dark, flat, matte roof field when rigid raised ribs and metal edge details are not resolved.

### 4917406019 — 12364 W Alameda Pkwy

- Primary type: **PVC or Coated Roof**
- The apparent finish is highly weathered, which can expose or visually emphasize underlying roof texture and repairs.
- Do not classify it as TPO merely because portions appear light in the aerial image.
- Roof condition and roof material remain separate decisions: weathering supports a coating interpretation only when coating-specific application variation, patchwork, wear-through, or underlying details are also visible.

### 4917423001 — 12250 W Kentucky Dr

- Primary/largest system: modified bitumen
- Secondary type: TPO on the white section
- The dominant tan fields have no clearly resolved membrane-sheet seams and show visible wear consistent with weathered modified bitumen at this image scale.
- Preserve the white TPO section as a separate roof zone.

## Calibration Rules Derived From Review

1. Return `metal` as the material family unless a subtype is clearly resolved.
2. Default an unresolved white TPO/PVC/coating comparison to TPO with reduced confidence, but do not apply that default when asphaltic weathering, aggregate, or coating evidence points to another family.
3. Use the controlled label **EPDM or Modified Bitumen** when a dark membrane is visible but the image cannot support choosing between them.
4. Use the controlled label **Modified Bitumen or Coated Roof** when weathered asphaltic roofing cannot be distinguished from a coating.
5. Preserve small materially distinct sections even when one roof type dominates the building.
6. Poor, soft, or compressed imagery must reduce confidence even when a reviewer can establish the material family. Do not express high confidence when the image cannot resolve the distinguishing profile, seam, edge, or surface cues.
7. Dense, regular, full-field panel lines on a rigid rectangular roof can support generic `metal` at reduced confidence even when the image is too soft to establish the metal subtype.
8. A dark, flat, matte attached roof without resolved raised ribs or metal edge details should favor EPDM over metal when broad membrane character is visible.
9. A weathered, monolithic finish with irregular application variation, underlying repairs, and wear-through can support `pvc_or_coating`; do not default such a surface to TPO.
10. Tan weathered asphaltic fields can be modified bitumen even when roll laps fall below aerial resolution, particularly when they are materially distinct from an adjacent white TPO zone.
11. Standard aerial imagery cannot reliably distinguish PVC from a coated roof at this resolution. Use the controlled final label **PVC or Coated Roof** instead of returning either material alone.
