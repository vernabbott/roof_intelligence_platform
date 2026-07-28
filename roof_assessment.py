#!/usr/bin/env python3
"""Canonical roof-assessment normalization shared by reports and revisions."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Mapping

from report_summary_config import REPORT_SUMMARY_CONFIG, append_with_limit, finalize_narrative
from roof_information_config import ROOF_TYPE_LABELS


ASSESSMENT_SYNC_VERSION = "roof-assessment-v1"
AMBIGUOUS_WHITE_SINGLE_PLY_KEY = "tpo_pvc_or_coating"
BREAKDOWN_WEIGHTS = {
    "Membrane Condition": 0.30,
    "Ponding": 0.20,
    "Flashing & Seals": 0.20,
    "Penetrations": 0.15,
    "Overall Maintenance": 0.15,
}
CONFIRMED_TREE_PHRASES = (
    "overhanging tree",
    "overhanging trees",
    "tree overhang",
    "tree canopy",
    "trees closely",
    "tree immediately adjacent",
    "trees immediately adjacent",
    "branches touching",
    "branches overhang",
    "branches extending over",
)
TREE_TERMS = ("tree", "trees", "branch", "branches", "canopy")
DEBRIS_TERMS = (
    "roof debris",
    "debris accumulation",
    "visible debris",
    "leaf accumulation",
    "leaves on the roof",
)
CUSTOMER_NARRATIVE_PROCESS_TERMS = (
    "reference image",
    "reference file",
    "reviewer-confirmed",
    "reviewer confirmed",
    "same-building match",
    "known-building match",
    "known building match",
    "matched on parcel",
    "imagery source",
    "material label is locked",
    "ground truth",
    "roof-reference workflow",
)


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _capitalize_sentence_starts(text: str) -> str:
    """Capitalize the first letter at the start of every sentence."""
    characters = list(text)
    capitalize_next = True
    possible_sentence_end = False
    closing_punctuation = "\"')]}”’"

    for index, character in enumerate(characters):
        if capitalize_next and character.isalpha():
            characters[index] = character.upper()
            capitalize_next = False

        if character in ".!?":
            possible_sentence_end = True
        elif possible_sentence_end:
            if character.isspace():
                capitalize_next = True
                possible_sentence_end = False
            elif character not in closing_punctuation:
                possible_sentence_end = False

    return "".join(characters)


def _sentence(value: object) -> str:
    text = _capitalize_sentence_starts(_text(value).rstrip())
    if not text:
        return ""
    terminal_text = text.rstrip("\"')]}”’")
    return text if terminal_text and terminal_text[-1] in ".!?" else text + "."


def _customer_observation(value: object) -> str:
    """Return roof facts while excluding internal identification-process prose."""
    text = _text(value)
    lowered = text.lower()
    if not text or any(term in lowered for term in CUSTOMER_NARRATIVE_PROCESS_TERMS):
        return ""
    if any(extension in lowered for extension in (".jpg", ".jpeg", ".png", ".webp")):
        return ""
    text = re.sub(
        r"^(?:the\s+)?(?:aerial\s+)?imagery\s+(?:shows|indicates|reveals)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return _sentence(text)


def _score(value: object, default: int = 0) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return default


def condition_label_for_score(score: object) -> str:
    value = _score(score)
    if value >= 80:
        return "GOOD"
    if value >= 60:
        return "FAIR"
    return "POOR"


def risk_level_for_score(score: object) -> str:
    value = _score(score)
    if value >= 80:
        return "LOW"
    if value >= 60:
        return "MODERATE"
    return "HIGH"


def normalize_zone_materials(analysis: dict) -> None:
    """Use controlled ambiguity when the zone evidence cannot support chemistry."""
    zones = analysis.get("roof_zones")
    if not isinstance(zones, list):
        return

    for zone in zones:
        if not isinstance(zone, dict):
            continue
        key = _text(zone.get("roof_type")).lower()
        alternatives = {
            _text(value).lower()
            for value in zone.get("alternatives") or []
            if _text(value)
        }
        limitations = " ".join(
            _text(value).lower() for value in zone.get("limitations") or []
        )
        confidence = _score(zone.get("confidence"))

        if key in {"pvc", "coating"}:
            key = "pvc_or_coating"
        elif key == "tpo":
            unresolved_white_surface = {"pvc", "coating"}.issubset(alternatives) and (
                confidence <= 60
                or any(
                    phrase in limitations
                    for phrase in (
                        "cannot distinguish",
                        "cannot be separated",
                        "not resolved",
                        "not readable",
                        "unresolved",
                    )
                )
            )
            if unresolved_white_surface:
                key = AMBIGUOUS_WHITE_SINGLE_PLY_KEY

        if key in ROOF_TYPE_LABELS:
            zone["roof_type"] = key


def normalize_tree_evidence(analysis: dict) -> None:
    """Allow tree-impact findings only when nearby trees are explicitly confirmed."""
    factors = analysis.get("visual_risk_factors")
    if not isinstance(factors, dict):
        return

    notes = [_sentence(note) for note in factors.get("notes") or [] if _sentence(note)]
    observations = [
        _sentence(item) for item in analysis.get("observations") or [] if _sentence(item)
    ]
    evidence_text = " ".join(notes + observations).lower()
    state = _text(factors.get("tree_proximity")).lower()
    if state not in {"confirmed", "not_visible", "indeterminate"}:
        state = (
            "confirmed"
            if any(phrase in evidence_text for phrase in CONFIRMED_TREE_PHRASES)
            else "indeterminate"
        )
    factors["tree_proximity"] = state

    if state == "confirmed":
        return

    factors["notes"] = [
        note for note in notes if not any(term in note.lower() for term in TREE_TERMS)
    ]
    analysis["observations"] = [
        item
        for item in observations
        if not any(term in item.lower() for term in TREE_TERMS)
    ]
    has_visible_debris = any(term in evidence_text for term in DEBRIS_TERMS)
    if not has_visible_debris:
        factors["overhanging_trees_or_debris"] = False


PONDING_EVIDENCE_PHRASES = (
    "standing water",
    "retained water",
    "visible water",
    "basin-shaped",
    "sediment ring",
    "tide ring",
    "algae-like",
    "blocked drain",
    "drainage concentration",
    "recurring wet area",
)
PONDING_NEGATION_PHRASES = (
    "no affirmative ponding",
    "no distinct ponding",
    "no clear ponding",
    "no clear retained water",
    "no clear standing water",
    "no retained water",
    "no standing water",
    "no visible ponding",
    "ponding is not visible",
    "without ponding evidence",
)
PONDING_OBSERVATION_PHRASES = (
    "ponding",
    "ponded",
    "standing water",
    "retained water",
    "visible water",
    "water accumulation",
)


def normalize_ponding_evidence(analysis: dict) -> None:
    """Remove ponding from all-metal roofs and reject unsupported flags elsewhere."""
    factors = analysis.get("visual_risk_factors")
    if not isinstance(factors, dict):
        return

    zones = [zone for zone in analysis.get("roof_zones") or [] if isinstance(zone, Mapping)]
    zone_types = {_text(zone.get("roof_type")).lower() for zone in zones if _text(zone.get("roof_type"))}
    top_level_type = _text(analysis.get("roof_type")).lower()
    all_metal = zone_types == {"metal"} or (not zone_types and top_level_type == "metal")
    if all_metal:
        def includes_ponding(value: object) -> bool:
            text = _sentence(value).lower()
            return any(phrase in text for phrase in PONDING_OBSERVATION_PHRASES)

        factors["suspected_ponding"] = False
        factors["notes"] = [
            _sentence(value)
            for value in factors.get("notes") or []
            if _sentence(value) and not includes_ponding(value)
        ]
        analysis["observations"] = [
            _sentence(value)
            for value in analysis.get("observations") or []
            if _sentence(value) and not includes_ponding(value)
        ]
        for zone in zones:
            zone["supporting_cues"] = [
                _sentence(value)
                for value in zone.get("supporting_cues") or []
                if _sentence(value) and not includes_ponding(value)
            ]
        return

    if factors.get("suspected_ponding") is not True:
        return

    evidence: list[str] = [
        _sentence(value) for value in factors.get("notes") or [] if _sentence(value)
    ]
    evidence.extend(
        _sentence(value) for value in analysis.get("observations") or [] if _sentence(value)
    )
    for zone in analysis.get("roof_zones") or []:
        if not isinstance(zone, dict):
            continue
        evidence.extend(
            _sentence(value) for value in zone.get("supporting_cues") or [] if _sentence(value)
        )
    evidence_text = " ".join(evidence).lower()
    has_negative = any(phrase in evidence_text for phrase in PONDING_NEGATION_PHRASES)
    has_affirmative = any(phrase in evidence_text for phrase in PONDING_EVIDENCE_PHRASES)
    if has_negative or not has_affirmative:
        factors["suspected_ponding"] = False


def confirmed_tree_proximity(analysis: Mapping) -> bool:
    factors = analysis.get("visual_risk_factors")
    return isinstance(factors, Mapping) and factors.get("tree_proximity") == "confirmed"


def canonical_observations(analysis: dict, maximum: int = 5) -> list[str]:
    """Build the displayed observations from the same zone and risk evidence."""
    zones = analysis.get("roof_zones")
    if not isinstance(zones, list) or not zones:
        return [
            _customer_observation(item)
            for item in analysis.get("observations") or []
            if _customer_observation(item)
        ][:maximum]

    result: list[str] = []
    for zone in sorted(
        (item for item in zones if isinstance(item, dict)),
        key=lambda item: _score(item.get("estimated_area_percentage")),
        reverse=True,
    ):
        material = ROOF_TYPE_LABELS.get(_text(zone.get("roof_type")).lower())
        location = _text(zone.get("location")) or "Target roof area"
        if "reviewer" in location.lower() or "match" in location.lower():
            location = "Target roof area"
        cues = [
            _text(cue).rstrip(".")
            for cue in zone.get("supporting_cues") or []
            if _customer_observation(cue)
        ][:2]
        if not material:
            continue
        finding = f"{location}: {material} roofing is present"
        if cues:
            finding += ", with " + "; ".join(cue.lower() for cue in cues)
        result.append(_sentence(finding))
        if len(result) >= maximum:
            return result

    factors = analysis.get("visual_risk_factors")
    if isinstance(factors, Mapping):
        for note in factors.get("notes") or []:
            sentence = _customer_observation(note)
            if sentence and sentence not in result:
                result.append(sentence)
            if len(result) >= maximum:
                return result

    for item in analysis.get("observations") or []:
        sentence = _customer_observation(item)
        if sentence and sentence not in result:
            result.append(sentence)
        if len(result) >= maximum:
            break
    return result


def score_from_breakdown(analysis: Mapping) -> int:
    """Calculate the overall condition score from the five displayed components."""
    reported = _score(analysis.get("overall_score"), 0)
    breakdown = analysis.get("breakdown")
    if not isinstance(breakdown, Mapping):
        return reported
    weighted = 0.0
    total_weight = 0.0
    for field, weight in BREAKDOWN_WEIGHTS.items():
        value = breakdown.get(field)
        if value is None:
            continue
        weighted += _score(value, reported) * weight
        total_weight += weight
    return _score(weighted / total_weight, reported) if total_weight else reported


def formatted_capture_date(value: object) -> str:
    text = _text(value)
    digits = "".join(character for character in text if character.isdigit())
    if len(digits) >= 8:
        try:
            return datetime.strptime(digits[:8], "%Y%m%d").strftime("%m/%d/%Y")
        except ValueError:
            pass
    return text


def build_consistent_summary(
    analysis: Mapping,
    capture_date: object = "",
) -> str:
    """Derive the report summary from canonical material, observations, and score."""
    material = _text(analysis.get("roof_type")) or "Primary: Material not determined"
    score = _score(analysis.get("overall_score"))
    condition = _text(analysis.get("condition_label")) or condition_label_for_score(score)
    risk = _text(analysis.get("risk_level")) or risk_level_for_score(score)
    if material.lower().startswith("primary:"):
        material_details = material.split(":", 1)[1].strip()
        if "; Secondary:" in material_details:
            primary, secondary = material_details.split("; Secondary:", 1)
            summary = (
                f"The roof includes {primary.strip()} and {secondary.strip()} areas "
                f"and is in {condition.lower()} condition, scoring {score}/100 "
                f"with {risk.lower()} visible risk."
            )
        else:
            summary = (
                f"The {material_details} roof is in {condition.lower()} condition, "
                f"scoring {score}/100 with {risk.lower()} visible risk."
            )
    else:
        summary = (
            f"The roof is in {condition.lower()} condition, scoring {score}/100 "
            f"with {risk.lower()} visible risk."
        )
    factors = analysis.get("visual_risk_factors")
    active_labels: list[str] = []
    if isinstance(factors, Mapping):
        for key, factor_config in REPORT_SUMMARY_CONFIG.visual_risk_factors.items():
            if factors.get(key):
                label = (
                    factor_config.confirmed_tree_label
                    if key == "overhanging_trees_or_debris"
                    and confirmed_tree_proximity(analysis)
                    and factor_config.confirmed_tree_label
                    else factor_config.label
                )
                active_labels.append(label)
    if active_labels:
        summary = append_with_limit(
            summary,
            "Principal visible concerns include " + ", ".join(active_labels) + ".",
            REPORT_SUMMARY_CONFIG.summary_max_characters,
        )
    return finalize_narrative(
        summary,
        REPORT_SUMMARY_CONFIG.summary_max_characters,
        REPORT_SUMMARY_CONFIG.fallback_summary,
    )


__all__ = [
    "AMBIGUOUS_WHITE_SINGLE_PLY_KEY",
    "ASSESSMENT_SYNC_VERSION",
    "BREAKDOWN_WEIGHTS",
    "build_consistent_summary",
    "canonical_observations",
    "confirmed_tree_proximity",
    "condition_label_for_score",
    "formatted_capture_date",
    "normalize_zone_materials",
    "normalize_tree_evidence",
    "normalize_ponding_evidence",
    "risk_level_for_score",
    "score_from_breakdown",
]
