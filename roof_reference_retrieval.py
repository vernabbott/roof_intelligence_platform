#!/usr/bin/env python3
"""Deterministic roof-reference identity matching, normalization, and retrieval."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps

from roof_reference_config import (
    PROJECT_ROOT,
    LoadedRoofReference,
    RoofReferenceConfig,
    RoofReferenceImage,
)


NORMALIZATION_VERSION = "roof-reference-normalization-v1"
NORMALIZED_IMAGE_SIZE = 768
MASK_BACKGROUND = (96, 96, 96)
DEFAULT_MAX_REFERENCE_IMAGES = 8
DEFAULT_IMAGES_PER_TYPE = 2


@dataclass(frozen=True)
class KnownBuildingMatch:
    roof_type: str
    reference: RoofReferenceImage
    parcel_id: str
    image_source: str
    image_date: str
    basis: str = "parcel+imagery_source+imagery_date"

    def as_trace(self) -> dict:
        return {
            "matched": True,
            "roof_type": self.roof_type,
            "reference_image": str(self.reference.path.resolve().relative_to(PROJECT_ROOT.resolve())),
            "parcel_id": self.parcel_id,
            "image_source": self.image_source,
            "image_date": self.image_date,
            "basis": self.basis,
            "reviewer_confirmed": self.reference.reviewer_confirmed,
            "material_locked": True,
        }


@dataclass(frozen=True)
class RankedReference:
    roof_type: str
    reference: RoofReferenceImage
    normalized_path: Path
    similarity: float


def _normalized_text(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _normalized_date(value: object) -> str:
    digits = re.sub(r"[^0-9]+", "", str(value or ""))
    if len(digits) == 8:
        if digits[:4].isdigit() and 1900 <= int(digits[:4]) <= 2200:
            return digits
        return digits[4:] + digits[:4]
    return digits


def find_known_building_match(row: dict, config: RoofReferenceConfig) -> KnownBuildingMatch | None:
    parcel = _normalized_text(row.get("Parcel Number"))
    source = _normalized_text(row.get("Primary Aerial Source"))
    image_date = _normalized_date(row.get("Primary Aerial Photo Date"))
    if not parcel or not source or not image_date:
        return None

    matches: list[KnownBuildingMatch] = []
    for roof_type, item in config.roof_types.items():
        for reference in item.reference_images:
            if not reference.reviewer_confirmed:
                continue
            for identity in reference.known_buildings:
                if (
                    _normalized_text(identity.parcel_id) == parcel
                    and _normalized_text(identity.image_source) == source
                    and _normalized_date(identity.image_date) == image_date
                ):
                    matches.append(
                        KnownBuildingMatch(
                            roof_type=roof_type,
                            reference=reference,
                            parcel_id=identity.parcel_id,
                            image_source=identity.image_source,
                            image_date=identity.image_date,
                        )
                    )
    if len(matches) > 1:
        labels = ", ".join(f"{match.roof_type}:{match.reference.path.name}" for match in matches)
        raise RuntimeError(f"Conflicting reviewer-confirmed known-building matches: {labels}")
    return matches[0] if matches else None


def known_building_stage1(match: KnownBuildingMatch) -> dict:
    cue_text = "; ".join(match.reference.cues) or "Reviewer-confirmed reference identity match."
    return {
        "building_classification": "single",
        "roof_zones": [
            {
                "zone_id": "known_building",
                "location": "entire reviewer-confirmed roof",
                "estimated_area_percentage": 100,
                "visual_evidence": {
                    "color_family": "reviewer_confirmed",
                    "seam_pattern": "reviewer_confirmed",
                    "surface_texture": "reviewer_confirmed",
                    "perimeter_stone_transition": "not_applicable",
                    "ridge_pattern": "not_applicable",
                    "evidence_summary": cue_text,
                },
                "candidates": [
                    {
                        "roof_type": match.roof_type,
                        "confidence": 100,
                        "evidence": (
                            "Reviewer-confirmed match on parcel, imagery source, and imagery date "
                            f"to {match.reference.path.name}."
                        ),
                    }
                ],
                "limitations": [
                    "The material label is locked; aerial imagery still limits condition and assembly conclusions."
                ],
            }
        ],
        "overall_limitations": [
            "Roof material is reviewer-confirmed for this exact building and imagery date."
        ],
        "known_building_match": match.as_trace(),
    }


def lock_known_building_material(analysis: dict, match: KnownBuildingMatch) -> None:
    existing_zones = analysis.get("roof_zones") or []
    existing_types = [
        str(zone.get("roof_type") or "")
        for zone in existing_zones
        if isinstance(zone, dict) and zone.get("roof_type")
    ]
    alternatives = [key for key in existing_types if key != match.roof_type][:3]
    supporting_cues = [
        (
            "Reviewer-confirmed exact building and imagery match to "
            f"{match.reference.path.name}; roof material is locked as {match.roof_type}."
        ),
        *match.reference.cues[:4],
    ]
    analysis["building_classification"] = "single"
    analysis["roof_zones"] = [
        {
            "zone_id": "known_building",
            "location": "entire reviewer-confirmed target roof",
            "roof_type": match.roof_type,
            "estimated_area_percentage": 100,
            "confidence": 100,
            "supporting_cues": supporting_cues[:5],
            "alternatives": alternatives,
            "limitations": [
                "Material is reviewer-confirmed for this parcel, imagery source, and imagery date; "
                "condition and exact assembly remain limited by aerial imagery."
            ],
        }
    ]
    analysis["possible_roof_systems"] = [
        {
            "system": match.roof_type,
            "confidence": 100,
            "evidence": supporting_cues[0],
        }
    ]
    analysis["known_building_match"] = match.as_trace()


def _masked_foreground_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    width, height = image.size
    corners = (
        image.getpixel((0, 0)),
        image.getpixel((width - 1, 0)),
        image.getpixel((0, height - 1)),
        image.getpixel((width - 1, height - 1)),
    )
    background = corners[0]
    similar_corners = sum(
        max(abs(int(pixel[channel]) - int(background[channel])) for channel in range(3)) <= 8
        for pixel in corners
    )
    if similar_corners < 3 or max(background) - min(background) > 8:
        return None
    difference = ImageChops.difference(image, Image.new("RGB", image.size, background)).convert("L")
    binary = difference.point(lambda value: 255 if value > 14 else 0)
    bbox = binary.getbbox()
    if not bbox:
        return None
    left, top, right, bottom = bbox
    padding = max(2, round(max(right - left, bottom - top) * 0.02))
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(width, right + padding),
        min(height, bottom + padding),
    )


def normalized_roof_image(
    source_path: Path,
    crop_box: tuple[float, float, float, float] | None = None,
    cache_dir: Path | None = None,
) -> Path:
    source_path = source_path.resolve()
    crop_signature = ",".join(f"{value:.6f}" for value in crop_box) if crop_box else "auto"
    digest = hashlib.sha256(
        NORMALIZATION_VERSION.encode("utf-8")
        + source_path.read_bytes()
        + crop_signature.encode("utf-8")
    ).hexdigest()
    output_dir = cache_dir or (PROJECT_ROOT / "tmp/roof_reference_normalized")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{digest}.png"
    if output_path.exists():
        return output_path

    with Image.open(source_path) as raw:
        image = raw.convert("RGB")
    if crop_box:
        width, height = image.size
        left, top, right, bottom = crop_box
        image = image.crop(
            (
                round(left * width),
                round(top * height),
                round(right * width),
                round(bottom * height),
            )
        )
    else:
        foreground = _masked_foreground_bbox(image)
        if foreground:
            image = image.crop(foreground)

    image.thumbnail((NORMALIZED_IMAGE_SIZE, NORMALIZED_IMAGE_SIZE), Image.Resampling.LANCZOS)
    normalized = Image.new("RGB", (NORMALIZED_IMAGE_SIZE, NORMALIZED_IMAGE_SIZE), MASK_BACKGROUND)
    normalized.paste(
        image,
        (
            (NORMALIZED_IMAGE_SIZE - image.width) // 2,
            (NORMALIZED_IMAGE_SIZE - image.height) // 2,
        ),
    )
    normalized.save(output_path, "PNG", optimize=True)
    return output_path


def _pearson_similarity(first: list[float], second: list[float]) -> float:
    first_mean = sum(first) / max(len(first), 1)
    second_mean = sum(second) / max(len(second), 1)
    centered_first = [value - first_mean for value in first]
    centered_second = [value - second_mean for value in second]
    denominator = math.sqrt(
        sum(value * value for value in centered_first)
        * sum(value * value for value in centered_second)
    )
    if not denominator:
        return 0.0
    return sum(a * b for a, b in zip(centered_first, centered_second)) / denominator


def _color_histogram(image: Image.Image) -> list[float]:
    histogram = [0.0] * 64
    count = 0
    resized = image.resize((64, 64), Image.Resampling.BILINEAR)
    pixel_source = getattr(resized, "get_flattened_data", resized.getdata)
    for red, green, blue in pixel_source():
        if max(abs(red - 96), abs(green - 96), abs(blue - 96)) <= 4:
            continue
        bucket = (red // 64) * 16 + (green // 64) * 4 + (blue // 64)
        histogram[bucket] += 1
        count += 1
    if count:
        histogram = [value / count for value in histogram]
    return histogram


def _normalized_values(image: Image.Image) -> list[float]:
    pixel_source = getattr(image, "get_flattened_data", image.getdata)
    return [value / 255 for value in pixel_source()]


def image_similarity(first_path: Path, second_path: Path) -> float:
    with Image.open(first_path) as first_raw:
        first = first_raw.convert("RGB")
    with Image.open(second_path) as second_raw:
        second = second_raw.convert("RGB")

    first_gray = ImageOps.grayscale(first).resize((32, 32), Image.Resampling.BILINEAR)
    first_values = _normalized_values(first_gray)
    first_edges = _normalized_values(
        ImageOps.grayscale(first)
        .filter(ImageFilter.FIND_EDGES)
        .resize((16, 16), Image.Resampling.BILINEAR)
    )
    spatial_scores: list[float] = []
    edge_scores: list[float] = []
    # Aerial exports are north-up. Supporting only 0° and 180° keeps retrieval
    # deterministic and prevents unrelated rectangular roofs from winning
    # merely because a 90° rotation happens to align their generic outlines.
    for angle in (0, 180):
        rotated = second.rotate(angle, expand=False)
        gray = ImageOps.grayscale(rotated).resize((32, 32), Image.Resampling.BILINEAR)
        spatial_scores.append(
            (_pearson_similarity(first_values, _normalized_values(gray)) + 1) / 2
        )
        edges = ImageOps.grayscale(rotated).filter(ImageFilter.FIND_EDGES).resize(
            (16, 16), Image.Resampling.BILINEAR
        )
        edge_scores.append(
            (_pearson_similarity(first_edges, _normalized_values(edges)) + 1) / 2
        )
    histogram_score = sum(
        min(a, b) for a, b in zip(_color_histogram(first), _color_histogram(second))
    )
    score = 0.55 * max(spatial_scores) + 0.30 * histogram_score + 0.15 * max(edge_scores)
    return round(max(0.0, min(score, 1.0)), 6)


def rank_references(
    selected_keys: list[str] | tuple[str, ...],
    config: RoofReferenceConfig,
    target_path: Path,
    cache_dir: Path | None = None,
) -> tuple[Path, list[RankedReference]]:
    normalized_target = normalized_roof_image(target_path, cache_dir=cache_dir)
    ranked: list[RankedReference] = []
    for roof_type in selected_keys:
        item = config.roof_types.get(roof_type)
        if not item:
            continue
        for reference in item.reference_images:
            normalized_reference = normalized_roof_image(
                reference.path,
                crop_box=reference.crop_box,
                cache_dir=cache_dir,
            )
            ranked.append(
                RankedReference(
                    roof_type=roof_type,
                    reference=reference,
                    normalized_path=normalized_reference,
                    similarity=image_similarity(normalized_target, normalized_reference),
                )
            )
    ranked.sort(key=lambda item: (-item.similarity, item.roof_type, item.reference.path.name))
    return normalized_target, ranked


def retrieve_reference_bundle(
    selected_keys: list[str] | tuple[str, ...],
    config: RoofReferenceConfig,
    target_path: Path,
    known_match: KnownBuildingMatch | None = None,
    max_images: int = DEFAULT_MAX_REFERENCE_IMAGES,
    images_per_type: int = DEFAULT_IMAGES_PER_TYPE,
    cache_dir: Path | None = None,
) -> tuple[Path, list[LoadedRoofReference]]:
    normalized_target, ranked = rank_references(selected_keys, config, target_path, cache_dir)
    maximum = max(1, int(max_images))
    per_type_limit = max(1, int(images_per_type))
    selected: list[RankedReference] = []
    selected_paths: set[Path] = set()
    per_type_counts: dict[str, int] = {}

    def add(candidate: RankedReference) -> None:
        if len(selected) >= maximum or candidate.reference.path in selected_paths:
            return
        if per_type_counts.get(candidate.roof_type, 0) >= per_type_limit:
            return
        selected.append(candidate)
        selected_paths.add(candidate.reference.path)
        per_type_counts[candidate.roof_type] = per_type_counts.get(candidate.roof_type, 0) + 1

    if known_match:
        for candidate in ranked:
            if candidate.reference.path == known_match.reference.path:
                add(candidate)
                break

    for roof_type in selected_keys:
        candidate = next((item for item in ranked if item.roof_type == roof_type), None)
        if candidate:
            add(candidate)
    for candidate in ranked:
        add(candidate)

    bundle: list[LoadedRoofReference] = []
    for roof_type in selected_keys:
        matches = [item for item in selected if item.roof_type == roof_type]
        if not matches:
            continue
        item = config.roof_types[roof_type]
        bundle.append(
            LoadedRoofReference(
                key=roof_type,
                label=item.label,
                guide_path=item.guide_path,
                guide_text=item.guide_path.read_text(encoding="utf-8"),
                image_paths=tuple(match.normalized_path for match in matches),
                source_image_paths=tuple(match.reference.path for match in matches),
                similarity_scores=tuple(match.similarity for match in matches),
            )
        )
    return normalized_target, bundle
