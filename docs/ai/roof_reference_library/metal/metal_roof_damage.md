---
status: draft
---

# Metal Roof Damage Identification

## Description

This file provides a starting reference for identifying and documenting visible damage on metal roof surfaces, including standing-seam, exposed-fastener, structural panel, and metal retrofit systems. Damage observations may include corrosion, coating loss, dents, punctures, loose or missing fasteners, displaced panels, seam separation, failed sealants, flashing defects, and deformation caused by impact, wind, thermal movement, or foot traffic.

## Why It's Important

Metal roofing depends on intact panels, seams, fasteners, clips, coatings, flashings, and sealants to shed water and accommodate movement. Small failures can allow corrosion or moisture entry to progress beneath panels, while loose components may create wind-uplift and falling-object hazards. Consistent damage identification supports timely maintenance, leak prevention, structural review, coating decisions, and accurate assessment of remaining service life.

## Visual Characteristics

### Aging

- Faded, chalked, peeling, blistered, scratched, or missing protective coating
- Red rust, white oxidation, pitting, scaling, galvanic corrosion, or perforation
- Deteriorated sealants, closures, washers, fasteners, and flashing details
- Widened fastener holes and wear associated with repeated thermal movement

### Ponding

- Standing water or staining on low-slope panels, behind curbs, or near clogged gutters
- Sediment, algae, debris lines, and corrosion concentrated in persistent wet areas
- Deflected panel flats or low spots that interrupt normal drainage
- Rust, coating failure, or failed seams along the perimeter of ponding areas

### Leaking

- Open panel laps, separated standing seams, missing fasteners, or failed washers
- Cracked or missing sealant at penetrations, closures, ridge caps, and terminations
- Rust trails, water staining, or corrosion extending from a joint or fastener
- Displaced flashing, punctures, perforation, and improperly lapped components

### Hail Damage

- Repeated circular dents or dimples across panel flats and ribs
- Dented vents, ridge caps, gutters, flashings, and rooftop equipment
- Chipped coating or exposed metal centered within impact marks
- Cracked seams, punctures, or fractured accessories from severe impacts

### Deformation

- Dents, creases, buckling, oil canning, crushed ribs, or panel deflection
- Shifted, uplifted, missing, or misaligned panels
- Distorted standing seams and laps that no longer engage uniformly
- Warping associated with thermal movement, foot traffic, impact, or structural movement

### Splitting

- Cracks or tears in panel flats, ribs, folds, and formed transitions
- Split seams, fractured solder joints, or separated panel laps
- Torn or elongated metal around fasteners and clips
- Cracked flashings and accessories at high-movement or high-stress locations

## AI Confidence Factors

AI confidence should account for reflections, panel geometry, normal oil canning, and the difficulty of evaluating fasteners from distant imagery.

### High Confidence

- Missing panels, open seams, holes, severe corrosion, or displaced flashing is clearly visible
- Damage interrupts otherwise regular panel ribs, seams, or fastener patterns
- Multiple images or angles confirm deformation or material loss
- Image scale resolves fastener, sealant, coating, or corrosion details
- Shadows and reflections are consistent with a physical defect rather than glare

### Medium Confidence

- Dents, corrosion, coating loss, or backed-out fasteners are likely but not sharply resolved
- Panel waviness may represent damage or normal oil canning
- Glare, roof color, moisture, or viewing angle affects the apparent condition
- Only one image or angle is available

### Low Confidence

- Bright or dark areas could be reflections, shadows, dirt, wet panels, or coating variation
- Fasteners and seams are below the useful image-resolution limit
- Apparent deformation follows image stitching or perspective distortion
- The metal system type or affected component cannot be confirmed

Low- and medium-confidence findings should be verified with closer imagery and hands-on inspection, including concealed clips and underside conditions when warranted.

## Severity

Severity should consider watertightness, corrosion depth, panel displacement, wind-uplift potential, structural deformation, and safety hazards.

### Minor

Cosmetic fading, light chalking, superficial scratches, isolated small dents, or minor surface oxidation without exposed base metal deterioration, seam failure, or leak indication. Monitor and maintain coatings as appropriate.

### Moderate

Localized coating failure, developing corrosion, multiple dents, loose fasteners, deteriorated sealant, or minor flashing displacement that could permit moisture entry or accelerate deterioration. Schedule professional maintenance and repair.

### Severe

Open seams, missing or backed-out fasteners across an area, advanced corrosion, punctures, displaced panels, failed flashing, or significant impact deformation. Prioritize prompt repair and assess concealed moisture or structural effects.

### Critical

Extensive panel loss or uplift, widespread perforation, unstable components, major structural deformation, active water intrusion, or loose metal presenting an immediate safety hazard. Escalate for urgent professional and structural assessment.

## Example Images

### Aging

#### Aging Example 1

![Metal roof aging example 1](images/aging_001.png)

#### Aging Example 2

![Metal roof aging example 2](images/aging_002.png)

### Ponding

Do not report ponding as an observation or visible-risk factor on an all-metal
roof. Set `suspected_ponding` to false and remove ponding, standing-water, and
retained-water wording from customer-facing observations and notes. Metal panel
roofs are treated as shedding water by design. A separately visible gutter,
drain, deformation, or structural concern may be documented by its physical
name without labeling the roof field as ponded.

### Leaking

### Penetration Repair Patches and Leak Potential

![Bright metal roof with localized repair patches around penetrations](images/metal_009.png)

Several localized contrasting patches surround penetrations and curbs on this
bright ribbed metal roof. Their concentration at leak-prone details supports a
history of repair activity and elevated flashing or seal leakage risk. Do not
state that active leakage is present from patches alone; confirm current
moisture entry, fastener and seam condition, and insulation moisture onsite.
When the panels remain sound, dry, compatible, and repairable, this type of
continuous metal field may warrant evaluation for silicone restoration after
required repairs, preparation, moisture testing, and adhesion testing.

### Fiberglass Skylight Protection During Restoration

![Metal roof with repeated translucent fiberglass skylight panels](images/metal_010.png)

The evenly spaced narrow rectangles aligned within this metal roof's rib grid are
translucent fiberglass skylight panels. They are roof openings and fall-through
hazards, not coating wear or repair patches. A silicone-restoration scope must
exclude the light-transmitting faces and require masking and protection so the
panels remain translucent and visibly identifiable. Inspect panel brittleness,
cracking, fasteners, perimeter seals, and safe-access requirements onsite; aerial
imagery alone cannot establish those conditions.

![Two-tone pitched metal roof with rib-aligned fiberglass skylights](images/metal_012.png)

This second reviewer-confirmed example shows lighter rectangular fiberglass
skylight panels repeated across a blue-gray metal roof section. Their organized
spacing and alignment within the same perpendicular rib grid distinguish them
from random repairs and from the adjacent cream-colored metal section. The
color transition does not establish damage or a different roofing material.
Inspect the skylight panels, perimeter seals, and safe-access requirements
onsite, and exclude and protect their light-transmitting faces during any
silicone-restoration work.

### Replaced Metal Panel Sections

![Metal roof with uniform-width replacement panel sections](images/metal_011.png)

The contrasting bright rectangles on this roof align with the narrow rib grid and
occupy consistent panel-bay widths. That modular alignment supports replacement
metal panel sections and prior repair activity rather than random membrane
patching. Document the repaired locations and inspect endlaps, sidelaps, fasteners,
sealants, and the reason for replacement onsite. Aerial imagery does not establish
whether the repaired sections are currently watertight.

### Hail Damage

No metal-roof hail-damage example images have been added yet.

### Deformation

No metal-roof deformation example images have been added yet.

### Splitting

No metal-roof splitting example images have been added yet.
