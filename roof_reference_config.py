#!/usr/bin/env python3
"""Validated configuration and file loading for AI roof-reference classification."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_ROOF_REFERENCE_MANIFEST_PATH = PROJECT_ROOT / "docs/ai/roof_reference_manifest.yaml"
ROOF_REFERENCE_FEATURE_ENV = "ROOF_REFERENCE_CLASSIFICATION"
METAL_MEMBRANE_RESOLVER_ENV = "ROOF_METAL_MEMBRANE_RESOLVER"
CONFIRMED_ZONE_ROOF_TYPES = {
    "tpo",
    "tpo_pvc_or_coating",
    "pvc",
    "epdm",
    "ballasted",
    "metal",
    "mod_bit",
    "tar_and_gravel",
    "coating",
    "pvc_or_coating",
    "epdm_or_mod_bit",
    "mod_bit_or_coating",
    "mod_bit_coating_or_tar_and_gravel",
    "mod_bit_or_tar_and_gravel",
    "ballasted_or_tar_and_gravel",
    "unknown",
}


class RoofReferenceConfigurationError(ValueError):
    """Raised when the roof-reference manifest or an approved file is invalid."""


@dataclass(frozen=True)
class RoofReferenceIdentity:
    parcel_id: str
    image_source: str
    image_date: str


@dataclass(frozen=True)
class ConfirmedRoofZone:
    zone_id: str
    location: str
    roof_type: str
    estimated_area_percentage: int
    cues: tuple[str, ...]
    alternatives: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class RoofReferenceImage:
    path: Path
    crop_box: tuple[float, float, float, float] | None
    known_buildings: tuple[RoofReferenceIdentity, ...]
    cues: tuple[str, ...]
    condition_tags: tuple[str, ...]
    reviewer_confirmed: bool
    confirmed_zones: tuple[ConfirmedRoofZone, ...]


@dataclass(frozen=True)
class RoofReferenceType:
    key: str
    label: str
    aliases: tuple[str, ...]
    guide_path: Path
    reference_images: tuple[RoofReferenceImage, ...]

    @property
    def reference_image_paths(self) -> tuple[Path, ...]:
        return tuple(image.path for image in self.reference_images)


@dataclass(frozen=True)
class KnownBuildingCorrection:
    roof_type: str
    reference: RoofReferenceImage


@dataclass(frozen=True)
class RoofReferenceConfig:
    workflow_version: str
    manifest_path: Path
    classification_guide_path: Path
    maximum_candidate_types: int
    confusion_groups: tuple[tuple[str, ...], ...]
    roof_types: dict[str, RoofReferenceType]
    known_building_corrections: tuple[KnownBuildingCorrection, ...]


@dataclass(frozen=True)
class LoadedRoofReference:
    key: str
    label: str
    guide_path: Path
    guide_text: str
    image_paths: tuple[Path, ...]
    source_image_paths: tuple[Path, ...] = ()
    similarity_scores: tuple[float, ...] = ()


def _mapping(value: Any, location: str) -> dict:
    if not isinstance(value, dict):
        raise RoofReferenceConfigurationError(f"{location} must be a YAML mapping")
    return value


def _text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoofReferenceConfigurationError(f"{location} must be non-empty text")
    return value.strip()


def _text_list(value: Any, location: str, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        qualifier = "a YAML list" if allow_empty else "a non-empty YAML list"
        raise RoofReferenceConfigurationError(f"{location} must be {qualifier}")
    return tuple(_text(item, f"{location}[{index}]") for index, item in enumerate(value))


def _project_path(value: Any, location: str, project_root: Path) -> Path:
    relative = Path(_text(value, location))
    if relative.is_absolute():
        raise RoofReferenceConfigurationError(f"{location} must be relative to the project root")
    root = project_root.resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RoofReferenceConfigurationError(f"{location} escapes the project root") from exc
    if not resolved.is_file():
        raise RoofReferenceConfigurationError(f"{location} does not exist: {relative}")
    return resolved


def _require_active_markdown(path: Path) -> None:
    document = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---", document, flags=re.DOTALL)
    if not match:
        raise RoofReferenceConfigurationError(f"{path} is missing YAML front matter")
    try:
        front_matter = _mapping(yaml.safe_load(match.group(1)), f"{path} front matter")
    except yaml.YAMLError as exc:
        raise RoofReferenceConfigurationError(f"Invalid YAML front matter in {path}: {exc}") from exc
    if str(front_matter.get("status", "")).strip().lower() != "active":
        raise RoofReferenceConfigurationError(f"{path} must have status: active before runtime use")


def _linked_markdown_images(path: Path, project_root: Path) -> tuple[Path, ...]:
    document = path.read_text(encoding="utf-8")
    linked: list[Path] = []
    root = project_root.resolve()
    for raw_target in re.findall(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+['\"][^'\"]*['\"])?\)", document):
        if re.match(r"^[a-z][a-z0-9+.-]*:", raw_target, flags=re.IGNORECASE):
            continue
        resolved = (path.parent / raw_target.strip("<>")).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise RoofReferenceConfigurationError(f"{path} image link escapes the project root: {raw_target}") from exc
        if not resolved.is_file():
            raise RoofReferenceConfigurationError(f"{path} image link does not exist: {raw_target}")
        linked.append(resolved)
    return tuple(linked)


def _reference_image(
    value: object,
    location: str,
    project_root: Path,
) -> RoofReferenceImage:
    if isinstance(value, str):
        path_value = value
        metadata: dict[str, Any] = {}
    else:
        metadata = _mapping(value, location)
        path_value = metadata.get("path")
    path = _project_path(path_value, f"{location}.path", project_root)

    raw_crop = metadata.get("crop_box")
    crop_box = None
    if raw_crop is not None:
        if (
            not isinstance(raw_crop, list)
            or len(raw_crop) != 4
            or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in raw_crop)
        ):
            raise RoofReferenceConfigurationError(f"{location}.crop_box must contain four numbers")
        crop_box = tuple(float(item) for item in raw_crop)
        left, top, right, bottom = crop_box
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            raise RoofReferenceConfigurationError(
                f"{location}.crop_box must be normalized [left, top, right, bottom] coordinates"
            )

    raw_identities = metadata.get("known_buildings") or []
    if not isinstance(raw_identities, list):
        raise RoofReferenceConfigurationError(f"{location}.known_buildings must be a YAML list")
    identities: list[RoofReferenceIdentity] = []
    for index, raw_identity in enumerate(raw_identities):
        identity_location = f"{location}.known_buildings[{index}]"
        identity = _mapping(raw_identity, identity_location)
        identities.append(
            RoofReferenceIdentity(
                parcel_id=_text(identity.get("parcel_id"), f"{identity_location}.parcel_id"),
                image_source=_text(identity.get("image_source"), f"{identity_location}.image_source"),
                image_date=_text(identity.get("image_date"), f"{identity_location}.image_date"),
            )
        )

    cues = _text_list(metadata.get("cues") or [], f"{location}.cues", allow_empty=True)
    condition_tags = _text_list(
        metadata.get("condition_tags") or [],
        f"{location}.condition_tags",
        allow_empty=True,
    )
    reviewer_confirmed = metadata.get("reviewer_confirmed", bool(identities))
    if not isinstance(reviewer_confirmed, bool):
        raise RoofReferenceConfigurationError(f"{location}.reviewer_confirmed must be true or false")
    if identities and not reviewer_confirmed:
        raise RoofReferenceConfigurationError(
            f"{location} cannot register known_buildings without reviewer_confirmed: true"
        )

    raw_zones = metadata.get("confirmed_zones") or []
    if not isinstance(raw_zones, list):
        raise RoofReferenceConfigurationError(f"{location}.confirmed_zones must be a YAML list")
    confirmed_zones: list[ConfirmedRoofZone] = []
    for index, raw_zone in enumerate(raw_zones):
        zone_location = f"{location}.confirmed_zones[{index}]"
        zone = _mapping(raw_zone, zone_location)
        area = zone.get("estimated_area_percentage")
        if not isinstance(area, int) or isinstance(area, bool) or not 1 <= area <= 100:
            raise RoofReferenceConfigurationError(
                f"{zone_location}.estimated_area_percentage must be an integer from 1 to 100"
            )
        confirmed_zones.append(
            ConfirmedRoofZone(
                zone_id=_text(zone.get("zone_id"), f"{zone_location}.zone_id"),
                location=_text(zone.get("location"), f"{zone_location}.location"),
                roof_type=_text(zone.get("roof_type"), f"{zone_location}.roof_type").lower(),
                estimated_area_percentage=area,
                cues=_text_list(zone.get("cues") or [], f"{zone_location}.cues", allow_empty=True),
                alternatives=_text_list(
                    zone.get("alternatives") or [],
                    f"{zone_location}.alternatives",
                    allow_empty=True,
                ),
                limitations=_text_list(
                    zone.get("limitations") or [],
                    f"{zone_location}.limitations",
                    allow_empty=True,
                ),
            )
        )
    if confirmed_zones and not reviewer_confirmed:
        raise RoofReferenceConfigurationError(
            f"{location} cannot register confirmed_zones without reviewer_confirmed: true"
        )
    if confirmed_zones and sum(zone.estimated_area_percentage for zone in confirmed_zones) != 100:
        raise RoofReferenceConfigurationError(
            f"{location}.confirmed_zones estimated_area_percentage values must total 100"
        )
    return RoofReferenceImage(
        path=path,
        crop_box=crop_box,
        known_buildings=tuple(identities),
        cues=cues,
        condition_tags=condition_tags,
        reviewer_confirmed=reviewer_confirmed,
        confirmed_zones=tuple(confirmed_zones),
    )


def load_roof_reference_config(
    manifest_path: str | Path = DEFAULT_ROOF_REFERENCE_MANIFEST_PATH,
    project_root: str | Path = PROJECT_ROOT,
) -> RoofReferenceConfig:
    root = Path(project_root)
    path = Path(manifest_path)
    try:
        raw = _mapping(yaml.safe_load(path.read_text(encoding="utf-8")), "roof reference manifest")
    except OSError as exc:
        raise RoofReferenceConfigurationError(f"Unable to read roof reference manifest: {path}") from exc
    except yaml.YAMLError as exc:
        raise RoofReferenceConfigurationError(f"Invalid roof reference manifest YAML: {exc}") from exc

    if raw.get("schema_version") not in {1, 2}:
        raise RoofReferenceConfigurationError("roof reference manifest schema_version must be 1 or 2")
    workflow_version = _text(raw.get("workflow_version"), "workflow_version")
    classification_guide_path = _project_path(raw.get("classification_guide"), "classification_guide", root)
    _require_active_markdown(classification_guide_path)

    maximum_candidate_types = raw.get("maximum_candidate_types")
    if not isinstance(maximum_candidate_types, int) or isinstance(maximum_candidate_types, bool):
        raise RoofReferenceConfigurationError("maximum_candidate_types must be an integer")
    if maximum_candidate_types < 1 or maximum_candidate_types > 7:
        raise RoofReferenceConfigurationError("maximum_candidate_types must be between 1 and 7")

    raw_types = _mapping(raw.get("roof_types"), "roof_types")
    roof_types: dict[str, RoofReferenceType] = {}
    for raw_key, raw_type in raw_types.items():
        key = str(raw_key).strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
            raise RoofReferenceConfigurationError(f"Invalid roof type key: {raw_key}")
        item = _mapping(raw_type, f"roof_types.{key}")
        if item.get("enabled") is not True:
            continue
        guide_path = _project_path(item.get("guide"), f"roof_types.{key}.guide", root)
        _require_active_markdown(guide_path)
        raw_reference_images = item.get("reference_images")
        if not isinstance(raw_reference_images, list) or not raw_reference_images:
            raise RoofReferenceConfigurationError(f"roof_types.{key}.reference_images must be a non-empty YAML list")
        reference_images = tuple(
            _reference_image(value, f"roof_types.{key}.reference_images[{index}]", root)
            for index, value in enumerate(raw_reference_images)
        )
        reference_paths = tuple(image.path for image in reference_images)
        if "stage2_images" in item:
            raise RoofReferenceConfigurationError(
                f"roof_types.{key}.stage2_images is obsolete; all approved reference_images entries "
                "are eligible for Stage 2 retrieval"
            )
        if len(set(reference_paths)) != len(reference_paths):
            raise RoofReferenceConfigurationError(f"roof_types.{key}.reference_images contains duplicates")
        guide_image_paths = _linked_markdown_images(guide_path, root)
        missing_from_manifest = [path for path in guide_image_paths if path not in reference_paths]
        missing_from_guide = [path for path in reference_paths if path not in guide_image_paths]
        if missing_from_manifest or missing_from_guide:
            details = []
            if missing_from_manifest:
                details.append(
                    "guide images missing from reference_images: "
                    + ", ".join(path.name for path in missing_from_manifest)
                )
            if missing_from_guide:
                details.append(
                    "reference_images missing from guide: "
                    + ", ".join(path.name for path in missing_from_guide)
                )
            raise RoofReferenceConfigurationError(f"roof_types.{key} image registration mismatch; " + "; ".join(details))
        roof_types[key] = RoofReferenceType(
            key=key,
            label=_text(item.get("label"), f"roof_types.{key}.label"),
            aliases=_text_list(item.get("aliases") or [], f"roof_types.{key}.aliases", allow_empty=True),
            guide_path=guide_path,
            reference_images=reference_images,
        )

    if not roof_types:
        raise RoofReferenceConfigurationError("roof_types must enable at least one roof type")

    for roof_type, item in roof_types.items():
        for reference in item.reference_images:
            for zone in reference.confirmed_zones:
                if zone.roof_type not in CONFIRMED_ZONE_ROOF_TYPES:
                    raise RoofReferenceConfigurationError(
                        f"{reference.path.name} confirmed zone {zone.zone_id} uses unsupported roof_type "
                        f"{zone.roof_type!r}"
                    )
                unknown_alternatives = [
                    key for key in zone.alternatives if key not in CONFIRMED_ZONE_ROOF_TYPES
                ]
                if unknown_alternatives:
                    raise RoofReferenceConfigurationError(
                        f"{reference.path.name} confirmed zone {zone.zone_id} uses unknown alternatives: "
                        + ", ".join(unknown_alternatives)
                    )
        zoned_references = [reference for reference in item.reference_images if reference.confirmed_zones]
        for reference in zoned_references:
            if roof_type not in {zone.roof_type for zone in reference.confirmed_zones}:
                raise RoofReferenceConfigurationError(
                    f"{reference.path.name} is registered under {roof_type} but no confirmed zone uses that type"
                )

    raw_corrections = raw.get("known_building_corrections") or []
    if not isinstance(raw_corrections, list):
        raise RoofReferenceConfigurationError("known_building_corrections must be a YAML list")
    corrections: list[KnownBuildingCorrection] = []
    for index, raw_correction in enumerate(raw_corrections):
        location = f"known_building_corrections[{index}]"
        correction = _mapping(raw_correction, location)
        correction_type = _text(correction.get("roof_type"), f"{location}.roof_type").lower()
        if correction_type not in CONFIRMED_ZONE_ROOF_TYPES:
            raise RoofReferenceConfigurationError(
                f"{location}.roof_type uses unsupported roof_type {correction_type!r}"
            )
        reference = _reference_image(correction, location, root)
        if not reference.reviewer_confirmed or not reference.known_buildings:
            raise RoofReferenceConfigurationError(
                f"{location} must be reviewer-confirmed and register at least one known building"
            )
        if reference.confirmed_zones and correction_type not in {
            zone.roof_type for zone in reference.confirmed_zones
        }:
            raise RoofReferenceConfigurationError(
                f"{location} has no confirmed zone using its roof_type {correction_type!r}"
            )
        for zone in reference.confirmed_zones:
            if zone.roof_type not in CONFIRMED_ZONE_ROOF_TYPES:
                raise RoofReferenceConfigurationError(
                    f"{location} confirmed zone {zone.zone_id} uses unsupported roof_type {zone.roof_type!r}"
                )
            unknown_alternatives = [
                key for key in zone.alternatives if key not in CONFIRMED_ZONE_ROOF_TYPES
            ]
            if unknown_alternatives:
                raise RoofReferenceConfigurationError(
                    f"{location} confirmed zone {zone.zone_id} uses unknown alternatives: "
                    + ", ".join(unknown_alternatives)
                )
        corrections.append(KnownBuildingCorrection(correction_type, reference))

    raw_groups = raw.get("confusion_groups") or []
    if not isinstance(raw_groups, list):
        raise RoofReferenceConfigurationError("confusion_groups must be a YAML list")
    groups: list[tuple[str, ...]] = []
    for index, raw_group in enumerate(raw_groups):
        group = _text_list(raw_group, f"confusion_groups[{index}]")
        unknown = [key for key in group if key not in roof_types]
        if unknown:
            raise RoofReferenceConfigurationError(
                f"confusion_groups[{index}] references disabled or unknown types: {', '.join(unknown)}"
            )
        groups.append(group)

    return RoofReferenceConfig(
        workflow_version=workflow_version,
        manifest_path=path.resolve(),
        classification_guide_path=classification_guide_path,
        maximum_candidate_types=maximum_candidate_types,
        confusion_groups=tuple(groups),
        roof_types=roof_types,
        known_building_corrections=tuple(corrections),
    )


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def roof_reference_feature_enabled(explicit_flag: bool = False) -> bool:
    return bool(explicit_flag or env_flag(ROOF_REFERENCE_FEATURE_ENV))


def metal_membrane_resolver_enabled() -> bool:
    """Return whether the disagreement-only material resolver is enabled."""
    return env_flag(METAL_MEMBRANE_RESOLVER_ENV)


def normalize_roof_type_key(value: object, config: RoofReferenceConfig) -> str:
    text = str(value or "").strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if normalized in config.roof_types:
        return normalized
    for key, item in config.roof_types.items():
        candidates = {item.label.lower(), *(alias.lower() for alias in item.aliases)}
        if text in candidates:
            return key
    return ""


def select_reference_types(stage1: dict, config: RoofReferenceConfig) -> list[str]:
    zones = stage1.get("roof_zones") if isinstance(stage1, dict) else []
    ranked_by_zone: list[list[str]] = []
    observed_candidate_keys: set[str] = set()
    leading_candidate_keys: set[str] = set()
    observed_color_families: set[str] = set()
    for zone in zones or []:
        if not isinstance(zone, dict):
            continue
        visual_evidence = zone.get("visual_evidence")
        if isinstance(visual_evidence, dict):
            color_family = str(visual_evidence.get("color_family") or "").strip().lower()
            if color_family:
                observed_color_families.add(color_family)
        candidates = zone.get("candidates") or []
        ranked = []
        for candidate_index, candidate in enumerate(candidates):
            value = candidate.get("roof_type") if isinstance(candidate, dict) else candidate
            observed = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
            if observed:
                observed_candidate_keys.add(observed)
                if candidate_index == 0:
                    leading_candidate_keys.add(observed)
            key = normalize_roof_type_key(value, config)
            if key and key not in ranked:
                ranked.append(key)
        if ranked:
            ranked_by_zone.append(ranked)

    selected: list[str] = []

    def add(key: str) -> None:
        # PVC is not a default companion for an ambiguous white roof. The
        # workflow defaults that case to TPO and loads PVC references only
        # when Stage 1 ranks PVC first for at least one zone.
        if key == "pvc" and "pvc" not in leading_candidate_keys:
            return
        if key in config.roof_types and key not in selected and len(selected) < config.maximum_candidate_types:
            selected.append(key)

    # Preserve the leading material family for every visible zone first.
    for ranked in ranked_by_zone:
        add(ranked[0])

    # Dark-membrane ambiguity must always receive both sides of the
    # EPDM/modified-bitumen comparison, regardless of candidate order.
    if {"epdm", "mod_bit"}.intersection(observed_candidate_keys):
        add("mod_bit")
        add("epdm")

    # Gray roofs need a direct weathered-TPO versus modified-bitumen
    # comparison even when Stage 1 returned only one side of that ambiguity.
    if observed_color_families.intersection({"light_gray", "gray"}) and {
        "tpo",
        "mod_bit",
    }.intersection(observed_candidate_keys):
        add("tpo")
        add("mod_bit")

    # A proposed coating can conceal an asphaltic substrate, so include the
    # modified-bitumen comparison even when coating is not the leading type.
    if "coating" in observed_candidate_keys:
        add("mod_bit")

    # A low-resolution tan or white aggregate field is often proposed as a
    # coating before individual ballast is resolved. Compare both families in
    # Stage 2 so positive ballast references can correct that ambiguity.
    if "coating" in observed_candidate_keys:
        add("tpo")
        add("ballasted")

    # Expand confusion pairs only from candidates Stage 1 actually observed.
    # Helper comparisons added above must not recursively pull in unrelated
    # material families. For example, adding modified bitumen as a coating
    # comparison must not then introduce metal to a smooth white membrane case.
    for group in config.confusion_groups:
        for key in group:
            if key in observed_candidate_keys:
                for companion in group:
                    add(companion)

    # Add second-ranked candidates only after direct ambiguity pairs have
    # reserved their slots.
    for ranked in ranked_by_zone:
        if len(ranked) > 1:
            add(ranked[1])

    for group in config.confusion_groups:
        for key in group:
            if key in observed_candidate_keys:
                if key in group:
                    for companion in group:
                        add(companion)

    for ranked in ranked_by_zone:
        for key in ranked[2:]:
            add(key)
    return selected


def load_reference_bundle(
    selected_keys: list[str] | tuple[str, ...],
    config: RoofReferenceConfig,
    images_per_type: int | None = None,
) -> list[LoadedRoofReference]:
    limit = None if images_per_type is None or int(images_per_type) <= 0 else int(images_per_type)
    bundle: list[LoadedRoofReference] = []
    for key in selected_keys:
        item = config.roof_types.get(key)
        if not item:
            continue
        bundle.append(
            LoadedRoofReference(
                key=key,
                label=item.label,
                guide_path=item.guide_path,
                guide_text=item.guide_path.read_text(encoding="utf-8"),
                image_paths=item.reference_image_paths[:limit],
                source_image_paths=item.reference_image_paths[:limit],
            )
        )
    return bundle


def relative_project_path(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))


def file_fingerprint(path: Path) -> dict:
    data = path.read_bytes()
    stat = path.stat()
    return {
        "path": relative_project_path(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "modified_ns": stat.st_mtime_ns,
    }


def roof_reference_trace(
    config: RoofReferenceConfig,
    bundle: list[LoadedRoofReference],
    stage1: dict,
    provider: str,
    model: str,
    status: str = "completed",
    known_building_match: dict | None = None,
    normalized_target_path: Path | None = None,
) -> dict:
    image_coverage = []
    retrieval = []
    for loaded in bundle:
        approved = config.roof_types[loaded.key].reference_image_paths
        used_sources = loaded.source_image_paths or loaded.image_paths
        image_coverage.append(
            {
                "roof_type": loaded.key,
                "approved_count": len(approved),
                "used_count": len(used_sources),
                "complete": used_sources == approved,
            }
        )
        for index, source_path in enumerate(used_sources):
            retrieval.append(
                {
                    "roof_type": loaded.key,
                    "source_image": relative_project_path(source_path),
                    "normalized_image": relative_project_path(loaded.image_paths[index]),
                    "similarity": (
                        loaded.similarity_scores[index]
                        if index < len(loaded.similarity_scores)
                        else None
                    ),
                }
            )
    source_paths = [
        path
        for item in bundle
        for path in (item.source_image_paths or item.image_paths)
    ]
    return {
        "enabled": True,
        "status": status,
        "workflow_version": config.workflow_version,
        "provider": provider,
        "model": model,
        "manifest": file_fingerprint(config.manifest_path),
        "classification_guide": file_fingerprint(config.classification_guide_path),
        "guides": [file_fingerprint(item.guide_path) for item in bundle],
        "reference_images": [file_fingerprint(path) for path in source_paths],
        "normalized_reference_images": [
            file_fingerprint(path) for item in bundle for path in item.image_paths
        ],
        "reference_image_coverage": image_coverage,
        "retrieval": retrieval,
        "normalized_target_image": (
            file_fingerprint(normalized_target_path) if normalized_target_path else None
        ),
        "known_building_match": known_building_match or {"matched": False},
        "stage1": stage1,
        "selected_reference_types": [item.key for item in bundle],
    }
