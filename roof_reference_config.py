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


class RoofReferenceConfigurationError(ValueError):
    """Raised when the roof-reference manifest or an approved file is invalid."""


@dataclass(frozen=True)
class RoofReferenceType:
    key: str
    label: str
    aliases: tuple[str, ...]
    guide_path: Path
    reference_image_paths: tuple[Path, ...]
    stage2_image_paths: tuple[Path, ...]


@dataclass(frozen=True)
class RoofReferenceConfig:
    workflow_version: str
    manifest_path: Path
    classification_guide_path: Path
    maximum_candidate_types: int
    confusion_groups: tuple[tuple[str, ...], ...]
    roof_types: dict[str, RoofReferenceType]


@dataclass(frozen=True)
class LoadedRoofReference:
    key: str
    label: str
    guide_path: Path
    guide_text: str
    image_paths: tuple[Path, ...]


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

    if raw.get("schema_version") != 1:
        raise RoofReferenceConfigurationError("roof reference manifest schema_version must be 1")
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
        reference_paths = tuple(
            _project_path(value, f"roof_types.{key}.reference_images[{index}]", root)
            for index, value in enumerate(_text_list(item.get("reference_images"), f"roof_types.{key}.reference_images"))
        )
        stage2_paths = tuple(
            _project_path(value, f"roof_types.{key}.stage2_images[{index}]", root)
            for index, value in enumerate(_text_list(item.get("stage2_images"), f"roof_types.{key}.stage2_images"))
        )
        if not set(stage2_paths).issubset(set(reference_paths)):
            raise RoofReferenceConfigurationError(f"roof_types.{key}.stage2_images must be approved reference_images")
        roof_types[key] = RoofReferenceType(
            key=key,
            label=_text(item.get("label"), f"roof_types.{key}.label"),
            aliases=_text_list(item.get("aliases") or [], f"roof_types.{key}.aliases", allow_empty=True),
            guide_path=guide_path,
            reference_image_paths=reference_paths,
            stage2_image_paths=stage2_paths,
        )

    if not roof_types:
        raise RoofReferenceConfigurationError("roof_types must enable at least one roof type")

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
    )


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def roof_reference_feature_enabled(explicit_flag: bool = False) -> bool:
    return bool(explicit_flag or env_flag(ROOF_REFERENCE_FEATURE_ENV))


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
    for zone in zones or []:
        if not isinstance(zone, dict):
            continue
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

    # Manifest order defines confusion-pair priority when the candidate limit
    # cannot accommodate every possible companion.
    for group in config.confusion_groups:
        for key in tuple(selected):
            if key in group:
                for companion in group:
                    add(companion)

    # Add second-ranked candidates only after mandatory ambiguity pairs have
    # reserved their slots.
    for ranked in ranked_by_zone:
        if len(ranked) > 1:
            add(ranked[1])

    for group in config.confusion_groups:
        for key in tuple(selected):
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
    images_per_type: int = 2,
) -> list[LoadedRoofReference]:
    limit = max(1, min(int(images_per_type), 4))
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
                image_paths=item.stage2_image_paths[:limit],
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
) -> dict:
    return {
        "enabled": True,
        "status": status,
        "workflow_version": config.workflow_version,
        "provider": provider,
        "model": model,
        "manifest": file_fingerprint(config.manifest_path),
        "classification_guide": file_fingerprint(config.classification_guide_path),
        "guides": [file_fingerprint(item.guide_path) for item in bundle],
        "reference_images": [file_fingerprint(path) for item in bundle for path in item.image_paths],
        "stage1": stage1,
        "selected_reference_types": [item.key for item in bundle],
    }
