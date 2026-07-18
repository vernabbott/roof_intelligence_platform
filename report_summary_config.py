#!/usr/bin/env python3
"""Validated report-summary configuration loaded from Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_REPORT_SUMMARY_PATH = Path(__file__).resolve().parent / "docs/ai/report_summary.md"


class ReportSummaryConfigurationError(ValueError):
    """Raised when the active report-summary configuration is invalid."""


@dataclass(frozen=True)
class VisualRiskFactorConfig:
    label: str
    indicators: tuple[str, ...]


@dataclass(frozen=True)
class ReportSummaryConfig:
    summary_max_characters: int
    recommendation_max_characters: int
    ai_guidance: str
    fallback_summary: str
    fallback_recommendation: str
    concern_template: str
    contractor_addendum: str
    visual_risk_factors: dict[str, VisualRiskFactorConfig]
    condition_terms: tuple[str, ...]
    risk_terms: tuple[str, ...]
    adjusted_condition_template: str


def _mapping(value: Any, location: str) -> dict:
    if not isinstance(value, dict):
        raise ReportSummaryConfigurationError(f"{location} must be a YAML mapping")
    return value


def _text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReportSummaryConfigurationError(f"{location} must be non-empty text")
    return value.strip()


def _positive_integer(value: Any, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ReportSummaryConfigurationError(f"{location} must be a positive integer")
    return value


def _text_list(value: Any, location: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ReportSummaryConfigurationError(f"{location} must be a non-empty YAML list")
    return tuple(_text(item, f"{location}[{index}]") for index, item in enumerate(value))


def _require_active(document: str, path: Path) -> None:
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---", document, flags=re.DOTALL)
    if not match:
        raise ReportSummaryConfigurationError(f"{path} is missing YAML front matter")
    try:
        front_matter = _mapping(yaml.safe_load(match.group(1)), f"{path} front matter")
    except yaml.YAMLError as exc:
        raise ReportSummaryConfigurationError(f"Invalid YAML front matter in {path}: {exc}") from exc
    if str(front_matter.get("status", "")).strip().lower() != "active":
        raise ReportSummaryConfigurationError(f"{path} must have status: active before it can drive report summaries")


def load_report_summary_config(path: str | Path = DEFAULT_REPORT_SUMMARY_PATH) -> ReportSummaryConfig:
    config_path = Path(path)
    try:
        document = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReportSummaryConfigurationError(f"Unable to read report-summary configuration: {config_path}") from exc

    _require_active(document, config_path)
    match = re.search(r"```yaml[ \t]+report_summary[ \t]*\r?\n(.*?)\r?\n```", document, flags=re.DOTALL)
    if not match:
        raise ReportSummaryConfigurationError(f"{config_path} is missing the labeled report_summary YAML block")
    try:
        config = _mapping(yaml.safe_load(match.group(1)), "report_summary")
    except yaml.YAMLError as exc:
        raise ReportSummaryConfigurationError(f"Invalid report_summary YAML in {config_path}: {exc}") from exc

    if config.get("schema_version") != 1:
        raise ReportSummaryConfigurationError("report_summary.schema_version must be 1")

    limits = _mapping(config.get("limits"), "report_summary.limits")
    fallback = _mapping(config.get("fallback"), "report_summary.fallback")
    visual_risk = _mapping(config.get("visual_risk"), "report_summary.visual_risk")
    raw_factors = _mapping(visual_risk.get("factors"), "report_summary.visual_risk.factors")
    factors: dict[str, VisualRiskFactorConfig] = {}
    for key, raw_factor in raw_factors.items():
        factor = _mapping(raw_factor, f"report_summary.visual_risk.factors.{key}")
        factors[str(key)] = VisualRiskFactorConfig(
            label=_text(factor.get("label"), f"report_summary.visual_risk.factors.{key}.label"),
            indicators=_text_list(factor.get("indicators"), f"report_summary.visual_risk.factors.{key}.indicators"),
        )

    required_factors = {
        "dark_staining_or_discoloration",
        "suspected_ponding",
        "high_penetration_density",
        "overhanging_trees_or_debris",
    }
    if set(factors) != required_factors:
        raise ReportSummaryConfigurationError(
            "report_summary.visual_risk.factors must define exactly: " + ", ".join(sorted(required_factors))
        )

    alignment = _mapping(config.get("condition_alignment"), "report_summary.condition_alignment")
    concern_template = _text(visual_risk.get("concern_template"), "report_summary.visual_risk.concern_template")
    adjusted_template = _text(
        alignment.get("adjusted_condition_template"),
        "report_summary.condition_alignment.adjusted_condition_template",
    )
    try:
        concern_template.format(labels="example")
        adjusted_template.format(condition="fair")
    except (KeyError, ValueError) as exc:
        raise ReportSummaryConfigurationError(f"Invalid report-summary template placeholder: {exc}") from exc

    return ReportSummaryConfig(
        summary_max_characters=_positive_integer(
            limits.get("summary_max_characters"), "report_summary.limits.summary_max_characters"
        ),
        recommendation_max_characters=_positive_integer(
            limits.get("recommendation_max_characters"), "report_summary.limits.recommendation_max_characters"
        ),
        ai_guidance=_text(config.get("ai_guidance"), "report_summary.ai_guidance"),
        fallback_summary=_text(fallback.get("summary"), "report_summary.fallback.summary"),
        fallback_recommendation=_text(fallback.get("recommendation"), "report_summary.fallback.recommendation"),
        concern_template=concern_template,
        contractor_addendum=_text(
            visual_risk.get("contractor_addendum"), "report_summary.visual_risk.contractor_addendum"
        ),
        visual_risk_factors=factors,
        condition_terms=_text_list(alignment.get("condition_terms"), "report_summary.condition_alignment.condition_terms"),
        risk_terms=_text_list(alignment.get("risk_terms"), "report_summary.condition_alignment.risk_terms"),
        adjusted_condition_template=adjusted_template,
    )


REPORT_SUMMARY_CONFIG = load_report_summary_config()


def append_with_limit(text: str, addition: str, maximum_characters: int) -> str:
    """Append required narrative while keeping the configured report-card limit."""
    base = str(text or "").strip()
    required = str(addition or "").strip()
    if not required or required.lower() in base.lower():
        return base[:maximum_characters].rstrip()
    available = maximum_characters - len(required) - 1
    if available <= 0:
        return required[:maximum_characters].rstrip()
    if len(base) > available:
        shortened = base[:available].rstrip()
        sentence_end = max(shortened.rfind("."), shortened.rfind("!"), shortened.rfind("?"))
        if sentence_end >= max(0, available // 2):
            shortened = shortened[: sentence_end + 1]
        else:
            shortened = shortened.rsplit(" ", 1)[0].rstrip(" ,;:") + "."
        base = shortened
    return f"{base} {required}".strip()
