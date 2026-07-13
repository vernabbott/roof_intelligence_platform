#!/usr/bin/env python3
# © PilotPoint IQ Roof Intelligence All rights reserved
"""Generate one-page roof intelligence PDF reports from building/parcel rows."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import shutil
import time
from datetime import date
from datetime import datetime
from math import cos, radians, sin
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

from roof_replacement_cost_estimator import (
    CostConfidenceInputs,
    estimate_roof_replacement_cost,
)


PAGE_W = 1700
PAGE_H = 2200
MARGIN = 42
BLUE = "#0057b8"
DARK_BLUE = "#0b1f44"
TEXT = "#111827"
MUTED = "#4b5563"
LIGHT = "#eef2f7"
BORDER = "#cbd5e1"
GREEN = "#58a832"
YELLOW = "#f3b700"
RED = "#e53935"
DEFAULT_PCS_LOGO_PATH = Path(__file__).resolve().parent / "public/images/PCS Logo.png"
DEFAULT_PILOTPOINTIQ_LOGO_PATH = Path(__file__).resolve().parent / "public/images/PilotPointIQ Logo.png"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Helvetica.ttf",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


FONT = {
    "brand": font(46, True),
    "title": font(42, True),
    "total_cost": font(30, True),
    "subtitle": font(24, False),
    "section": font(18, True),
    "body": font(17, False),
    "body_bold": font(17, True),
    "small": font(14, False),
    "small_bold": font(14, True),
    "footer": font(20, True),
    "score": font(92, True),
    "score_small": font(30, False),
}


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def first_row_value(row: dict, fields: tuple[str, ...]) -> str:
    for field in fields:
        value = normalize_text(row.get(field))
        if value:
            return value
    return ""


def aerial_source_label(row: dict) -> str:
    return first_row_value(row, ("Primary Aerial Source",)) or "Aerial imagery"


def aerial_photo_date_value(row: dict) -> str:
    return first_row_value(row, ("Primary Aerial Photo Date", "Denver GIS Aerial Photo Date"))


def aerial_image_file_value(row: dict) -> str:
    return first_row_value(row, ("Primary Aerial Image File", "Denver GIS Aerial Image File"))


def format_aerial_photo_date(value: object) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    formatted_dates: list[str] = []
    for token in text.replace(",", " ").split():
        if len(token) == 8 and token.isdigit():
            formatted_dates.append(f"{token[4:6]}/{token[6:8]}/{token[:4]}")
    if not formatted_dates:
        return text
    if len(formatted_dates) == 1 or formatted_dates[0] == formatted_dates[-1]:
        return formatted_dates[0]
    return f"{formatted_dates[0]} - {formatted_dates[-1]}"


def aerial_photo_dates(value: object) -> list[date]:
    dates: list[date] = []
    for token in normalize_text(value).replace(",", " ").split():
        if len(token) != 8 or not token.isdigit():
            continue
        try:
            dates.append(datetime.strptime(token, "%Y%m%d").date())
        except ValueError:
            continue
    return dates


def aerial_photo_age_years(row: dict, as_of: date | None = None) -> float:
    dates = aerial_photo_dates(aerial_photo_date_value(row))
    if not dates:
        return 0.0
    latest_photo_date = max(dates)
    report_date = as_of or date.today()
    if latest_photo_date >= report_date:
        return 0.0
    return (report_date - latest_photo_date).days / 365.25


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def shorten(value: object, max_chars: int) -> str:
    text = normalize_text(value)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


def int_value(value: object) -> int:
    try:
        return int(round(float(str(value or "0").replace(",", ""))))
    except ValueError:
        return 0


def format_int(value: object) -> str:
    number = int_value(value)
    return f"{number:,}" if number else ""


def format_currency(value: object) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"${amount:,.0f}"


def roof_squares(row: dict) -> int:
    sqft = int_value(row.get("Building Footprint Sq Ft"))
    return round(sqft / 100) if sqft else 0


def report_id(row: dict) -> str:
    seed = "|".join(
        [
            normalize_text(row.get("Parcel Number")),
            normalize_text(row.get("Address")),
            normalize_text(row.get("Building Footprint Sq Ft")),
        ]
    )
    return "RPT-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10].upper()


def resolve_path(base_dir: Path, value: str) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    if path.exists():
        return path

    file_name = Path(value).name
    if not file_name:
        return None
    for root_name in ("data", "CO"):
        search_root = base_dir / root_name
        if not search_root.exists():
            continue
        for candidate in search_root.rglob(file_name):
            if candidate.is_file():
                return candidate
    return None


def image_quality(path: Path | None) -> float:
    if not path or not path.exists():
        return -1
    try:
        with Image.open(path) as img:
            gray = img.convert("L").resize((256, 256))
            stat = ImageStat.Stat(gray)
            contrast = stat.stddev[0]
            brightness = stat.mean[0]
            width, height = img.size
            return (width * height / 1000.0) + contrast * 4.0 - abs(brightness - 130) * 0.4
    except OSError:
        return -1


def image_diagnostics(path: Path | None) -> dict:
    if not path or not path.exists():
        return {
            "exists": False,
            "blank": True,
            "width": 0,
            "height": 0,
            "brightness": 0.0,
            "contrast": 0.0,
            "reason": "missing",
        }
    try:
        with Image.open(path) as img:
            gray = img.convert("L").resize((256, 256))
            stat = ImageStat.Stat(gray)
            brightness = float(stat.mean[0])
            contrast = float(stat.stddev[0])
            width, height = img.size
            blank = contrast < 3.0 or brightness < 5.0 or brightness > 250.0
            return {
                "exists": True,
                "blank": blank,
                "width": width,
                "height": height,
                "brightness": round(brightness, 2),
                "contrast": round(contrast, 2),
                "reason": "blank_or_low_contrast" if blank else "",
            }
    except OSError as exc:
        return {
            "exists": False,
            "blank": True,
            "width": 0,
            "height": 0,
            "brightness": 0.0,
            "contrast": 0.0,
            "reason": f"unreadable: {exc}",
        }


def choose_best_image(denver_path: Path | None, drcog_path: Path | None) -> tuple[str, Path | None]:
    return "Primary aerial imagery", denver_path


def fallback_analysis(row: dict, best_source: str) -> dict:
    squares = roof_squares(row)
    age = 0
    if row.get("Year Built"):
        try:
            age = max(0, date.today().year - int(float(row["Year Built"])))
        except ValueError:
            age = 0
    base = 76
    if age > 40:
        base -= 7
    elif age > 25:
        base -= 4
    if squares > 2000:
        base -= 3
    score = max(52, min(88, base))
    label = "GOOD" if score >= 70 else "FAIR" if score >= 55 else "POOR"
    risk = "MODERATE" if score >= 55 else "HIGH"
    return {
        "source": "fallback",
        "best_image_source": best_source,
        "roof_type": "Low-slope membrane",
        "roof_system": "Unknown membrane",
        "possible_roof_systems": [],
        "roof_age_estimate": f"{age} years" if age else "Unknown",
        "roof_pitch": "Low slope",
        "overall_score": score,
        "condition_label": label,
        "risk_level": risk,
        "ai_confidence": 0,
        "visual_risk_factors": {
            "dark_staining_or_discoloration": False,
            "suspected_ponding": False,
            "high_penetration_density": False,
            "overhanging_trees_or_debris": False,
            "notes": [],
        },
        "observations": [
            "Aerial imagery is available, but AI analysis was not run for this report.",
            "Large low-slope roof area should be reviewed for membrane wear, drainage, staining, and penetration condition.",
            "Use the selected aerial image as the primary visual reference for field validation.",
        ],
        "breakdown": {
            "Membrane Condition": score,
            "Ponding": max(45, score - 12),
            "Flashing & Seals": max(45, score - 8),
            "Penetrations": max(50, score - 2),
            "Overall Maintenance": score,
        },
        "summary": (
            "This preliminary report was generated from parcel/building data and aerial imagery. "
            "AI roof observations were not requested or no API key was available, so condition values "
            "are conservative placeholders for layout and workflow validation."
        ),
        "recommendation": "Run AI image analysis and perform field inspection before final assessment.",
    }


def encode_image_data_url(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def image_mime_type(path: Path) -> str:
    return "image/png" if path.suffix.lower() == ".png" else "image/jpeg"


def encode_image_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def analysis_prompt(row: dict) -> str:
    source_label = aerial_source_label(row)
    return (
        f"Analyze this {source_label} aerial roof image for a commercial roof intelligence report. "
        "Use only visible image evidence and the provided property metadata. Return JSON only. "
        "Keep the narrative summary broad and avoid overstating exact membrane chemistry from aerial imagery alone. "
        "When visible evidence supports it, include possible roof system candidates such as TPO/PVC, EPDM, "
        "tar and gravel/BUR, modified bitumen, metal, ballasted membrane, or coating over membrane. "
        "For possible_roof_systems, list only systems supported by image evidence; use confidence values that reflect "
        "aerial-only uncertainty, and explain the visual cue in the evidence field. "
        "Score roof condition using visible serviceability risks, not only apparent membrane age. Darkened spots, "
        "uneven roof color, stains, algae-like dark areas, or localized discoloration can indicate recurring ponding, "
        "wet insulation, leaks, prior repairs, or water-damage potential. If those conditions are visible, reduce "
        "Membrane Condition, Ponding, Overall Maintenance, and the overall_score unless there is strong visible evidence "
        "they are benign shadows or equipment staining. Numerous penetrations, skylights, vents, curbs, or rooftop units "
        "on an older low-slope roof increase leak potential and should reduce Penetrations and Flashing & Seals. "
        "Trees overhanging or touching the roof, or visible leaf/debris accumulation, create puncture, abrasion, clogged "
        "drainage, and moisture-retention risk and should reduce Overall Maintenance and be noted. "
        "Use the full 0-100 scoring range: clean, uniform, well-drained roofs can score 80+, but visible ponding/staining "
        "or many leak-prone details should generally move the score into fair or poor territory. "
        "Include these concerns in visual_risk_factors, observations, summary, and recommendation when present. "
        "The aerial photo date may be older than the report date; note that older imagery can understate "
        "current deterioration, but do not apply a separate numerical age penalty to overall_score because "
        "the reporting system adjusts final scores for elapsed time after the image date. If a formatted aerial "
        "photo date is provided in metadata, reference that exact date instead of saying 'if the imagery is older'. "
        "Only use conditional age language when the aerial photo date is missing or unknown. "
        "Do not include underwriting snapshot or carrier appetite. Property metadata: "
        + json.dumps(
            {
                "address": row.get("Address"),
                "city": row.get("Building City"),
                "state": row.get("Building State"),
                "zip": row.get("Building ZIP"),
                "parcel": row.get("Parcel Number"),
                "year_built": row.get("Year Built"),
                "property_use": row.get("Property Use"),
                "building_footprint_sqft": row.get("Building Footprint Sq Ft"),
                "aerial_source": source_label,
                "aerial_photo_date": aerial_photo_date_value(row),
                "formatted_aerial_photo_date": format_aerial_photo_date(aerial_photo_date_value(row)),
            }
        )
    )


def analysis_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "best_image_source": {"type": "string"},
            "roof_type": {"type": "string"},
            "roof_system": {"type": "string"},
            "possible_roof_systems": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "system": {"type": "string"},
                        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                        "evidence": {"type": "string"},
                    },
                    "required": ["system", "confidence", "evidence"],
                },
                "minItems": 0,
                "maxItems": 4,
            },
            "roof_age_estimate": {"type": "string"},
            "roof_pitch": {"type": "string"},
            "overall_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "condition_label": {"type": "string"},
            "risk_level": {"type": "string"},
            "ai_confidence": {"type": "integer", "minimum": 0, "maximum": 100},
            "visual_risk_factors": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "dark_staining_or_discoloration": {"type": "boolean"},
                    "suspected_ponding": {"type": "boolean"},
                    "high_penetration_density": {"type": "boolean"},
                    "overhanging_trees_or_debris": {"type": "boolean"},
                    "notes": {"type": "array", "items": {"type": "string"}, "minItems": 0, "maxItems": 4},
                },
                "required": [
                    "dark_staining_or_discoloration",
                    "suspected_ponding",
                    "high_penetration_density",
                    "overhanging_trees_or_debris",
                    "notes",
                ],
            },
            "observations": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 5},
            "breakdown": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "Membrane Condition": {"type": "integer", "minimum": 0, "maximum": 100},
                    "Ponding": {"type": "integer", "minimum": 0, "maximum": 100},
                    "Flashing & Seals": {"type": "integer", "minimum": 0, "maximum": 100},
                    "Penetrations": {"type": "integer", "minimum": 0, "maximum": 100},
                    "Overall Maintenance": {"type": "integer", "minimum": 0, "maximum": 100},
                },
                "required": [
                    "Membrane Condition",
                    "Ponding",
                    "Flashing & Seals",
                    "Penetrations",
                    "Overall Maintenance",
                ],
            },
            "summary": {"type": "string"},
            "recommendation": {"type": "string"},
        },
        "required": [
            "best_image_source",
            "roof_type",
            "roof_system",
            "possible_roof_systems",
            "roof_age_estimate",
            "roof_pitch",
            "overall_score",
            "condition_label",
            "risk_level",
            "ai_confidence",
            "visual_risk_factors",
            "observations",
            "breakdown",
            "summary",
            "recommendation",
        ],
    }


def extract_response_text(response: dict) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    pieces: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                pieces.append(text)
    return "\n".join(pieces).strip()


def env_float(name: str) -> float:
    try:
        return float(os.environ.get(name, "0") or 0)
    except ValueError:
        return 0.0


def openai_usage_summary(response: dict) -> dict:
    usage = response.get("usage") or {}
    input_details = usage.get("input_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}
    summary = {
        "input_tokens": int(usage.get("input_tokens") or 0),
        "cached_input_tokens": int(input_details.get("cached_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "reasoning_output_tokens": int(output_details.get("reasoning_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }

    input_rate = env_float("OPENAI_INPUT_COST_PER_1M")
    cached_input_rate = env_float("OPENAI_CACHED_INPUT_COST_PER_1M")
    output_rate = env_float("OPENAI_OUTPUT_COST_PER_1M")
    if input_rate or cached_input_rate or output_rate:
        billable_input_tokens = max(summary["input_tokens"] - summary["cached_input_tokens"], 0)
        estimated_cost = (
            (billable_input_tokens / 1_000_000) * input_rate
            + (summary["cached_input_tokens"] / 1_000_000) * cached_input_rate
            + (summary["output_tokens"] / 1_000_000) * output_rate
        )
        summary["estimated_cost_usd"] = round(estimated_cost, 6)
        summary["pricing_env"] = {
            "OPENAI_INPUT_COST_PER_1M": input_rate,
            "OPENAI_CACHED_INPUT_COST_PER_1M": cached_input_rate,
            "OPENAI_OUTPUT_COST_PER_1M": output_rate,
        }
    return summary


def call_openai_analysis(row: dict, denver_path: Path | None, drcog_path: Path | None, model: str) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    content: list[dict] = [
        {
            "type": "input_text",
            "text": analysis_prompt(row),
        }
    ]
    if denver_path:
        content.append({"type": "input_text", "text": f"{aerial_source_label(row)} image:"})
        content.append({"type": "input_image", "image_url": encode_image_data_url(denver_path)})

    payload = {
        "model": model,
        "input": [{"role": "user", "content": content}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "roof_report_analysis",
                "schema": analysis_schema(),
                "strict": True,
            }
        },
        "max_output_tokens": 1400,
        "store": False,
    }
    request = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "PilotPointIQ Roof Report Generator",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            data = json.load(response)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"OpenAI API request failed: {exc}") from exc

    text = extract_response_text(data)
    if not text:
        raise RuntimeError("OpenAI API returned no analysis text")
    analysis = json.loads(text)
    analysis["source"] = "openai"
    analysis["usage"] = openai_usage_summary(data)
    return analysis


def extract_gemini_text(response: dict) -> str:
    pieces: list[str] = []
    for candidate in response.get("candidates", []):
        content = candidate.get("content") or {}
        for part in content.get("parts", []):
            text = part.get("text")
            if isinstance(text, str):
                pieces.append(text)
    return "\n".join(pieces).strip()


def parse_json_text(text: str) -> dict:
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.strip("`")
        if clean.lower().startswith("json"):
            clean = clean[4:].strip()
    start = clean.find("{")
    end = clean.rfind("}")
    if start >= 0 and end > start:
        clean = clean[start : end + 1]
    return json.loads(clean)


def analysis_source_label(analysis: dict) -> str:
    source = normalize_text(analysis.get("source")).lower()
    if source == "openai":
        return "OpenAI vision analysis"
    if source == "gemini":
        return "Gemini vision analysis"
    return "Fallback placeholder analysis"


def call_gemini_analysis(row: dict, denver_path: Path | None, drcog_path: Path | None, model: str) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    parts: list[dict] = [{"text": analysis_prompt(row)}]
    if denver_path:
        parts.append({"text": f"{aerial_source_label(row)} image:"})
        parts.append(
            {
                "inlineData": {
                    "mimeType": image_mime_type(denver_path),
                    "data": encode_image_base64(denver_path),
                }
            }
        )

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1400,
            "responseMimeType": "application/json",
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "PilotPointIQ Roof Report Generator",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            data = json.load(response)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini API error {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Gemini API request failed: {exc}") from exc

    text = extract_gemini_text(data)
    if not text:
        raise RuntimeError(f"Gemini API returned no analysis text: {data}")
    analysis = parse_json_text(text)
    analysis["source"] = "gemini"
    return analysis


def load_or_create_analysis(
    row: dict,
    denver_path: Path | None,
    drcog_path: Path | None,
    cache_dir: Path,
    use_ai: bool,
    provider: str,
    model: str,
    allow_ai_fallback: bool,
) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    parcel = normalize_text(row.get("Parcel Number")) or hashlib.sha1(json.dumps(row).encode("utf-8")).hexdigest()[:12]
    cache_path = cache_dir / f"{provider if use_ai else 'fallback'}-{parcel}.json"

    best_source, _ = choose_best_image(denver_path, drcog_path)
    cache_fallback = False
    if use_ai:
        try:
            if provider == "gemini":
                analysis = call_gemini_analysis(row, denver_path, drcog_path, model)
            else:
                analysis = call_openai_analysis(row, denver_path, drcog_path, model)
        except Exception as exc:
            if not allow_ai_fallback:
                raise RuntimeError(f"{provider} AI analysis failed for {parcel}: {exc}") from exc
            print(f"Warning: {provider} AI analysis failed for {parcel}: {exc}")
            analysis = fallback_analysis(row, best_source)
            cache_fallback = True
    else:
        analysis = fallback_analysis(row, best_source)

    if cache_fallback:
        cache_path = cache_dir / f"fallback-{parcel}.json"
    cache_path.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    return analysis


def fit_text_to_width(draw: ImageDraw.ImageDraw, text: str, font_obj, max_width: int) -> str:
    text = normalize_text(text)
    if text_width(draw, text, font_obj) <= max_width:
        return text
    ellipsis = "..."
    while text and text_width(draw, text + ellipsis, font_obj) > max_width:
        text = text[:-1].rstrip()
    return (text + ellipsis) if text else ellipsis


def wrap_text_lines(draw: ImageDraw.ImageDraw, text: str, font_obj, max_width: int) -> list[str]:
    words = normalize_text(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        if text_width(draw, word, font_obj) > max_width:
            if current:
                lines.append(current)
                current = ""
            chunk = ""
            for char in word:
                trial = chunk + char
                if text_width(draw, trial, font_obj) <= max_width:
                    chunk = trial
                else:
                    if chunk:
                        lines.append(chunk)
                    chunk = char
            if chunk:
                current = chunk
            continue

        trial = f"{current} {word}".strip()
        if text_width(draw, trial, font_obj) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    fill: str,
    font_obj,
    max_width: int | None = None,
    line_gap: int = 4,
    max_lines: int | None = None,
) -> int:
    x, y = xy
    if not max_width:
        draw.text((x, y), text, fill=fill, font=font_obj)
        return y + text_height(draw, text, font_obj)
    lines = wrap_text_lines(draw, text, font_obj, max_width)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fit_text_to_width(draw, lines[-1], font_obj, max_width)
    for line in lines:
        draw.text((x, y), line, fill=fill, font=font_obj)
        y += text_height(draw, line, font_obj) + line_gap
    return y


def text_height(draw: ImageDraw.ImageDraw, text: str, font_obj) -> int:
    bbox = draw.textbbox((0, 0), text or "Ag", font=font_obj)
    return bbox[3] - bbox[1]


def text_width(draw: ImageDraw.ImageDraw, text: str, font_obj) -> int:
    bbox = draw.textbbox((0, 0), text or "", font=font_obj)
    return bbox[2] - bbox[0]


def card(draw: ImageDraw.ImageDraw, xyxy: tuple[int, int, int, int], title: str | None = None) -> None:
    draw.rounded_rectangle(xyxy, radius=10, fill="white", outline=BORDER, width=2)
    if title:
        x1, y1, x2, _ = xyxy
        draw.text((x1 + 16, y1 + 12), title.upper(), fill=BLUE, font=FONT["section"])
        draw.line((x1 + 14, y1 + 42, x2 - 14, y1 + 42), fill=LIGHT, width=2)


def paste_fit(canvas: Image.Image, path: Path | None, box: tuple[int, int, int, int]) -> None:
    draw = ImageDraw.Draw(canvas)
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=8, fill="#f8fafc", outline=BORDER, width=2)
    if not path or not path.exists():
        draw.text((x1 + 20, y1 + 20), "Image unavailable", fill=MUTED, font=FONT["body"])
        return
    try:
        with Image.open(path) as src:
            img = src.convert("RGB")
            img.thumbnail((x2 - x1 - 8, y2 - y1 - 8), Image.LANCZOS)
            px = x1 + ((x2 - x1) - img.width) // 2
            py = y1 + ((y2 - y1) - img.height) // 2
            canvas.paste(img, (px, py))
    except OSError:
        draw.text((x1 + 20, y1 + 20), "Image unreadable", fill=MUTED, font=FONT["body"])


def paste_logo_fit(canvas: Image.Image, path: Path | None, box: tuple[int, int, int, int]) -> None:
    if not path or not path.exists():
        return
    x1, y1, x2, y2 = box
    try:
        with Image.open(path) as src:
            logo = src.convert("RGBA")
            logo.thumbnail((x2 - x1, y2 - y1), Image.Resampling.LANCZOS)
            px = x1 + ((x2 - x1) - logo.width) // 2
            py = y1 + ((y2 - y1) - logo.height) // 2
            canvas.paste(logo, (px, py), logo)
    except OSError:
        return


def paste_logo_trimmed_fit(canvas: Image.Image, path: Path | None, box: tuple[int, int, int, int]) -> None:
    if not path or not path.exists():
        return
    x1, y1, x2, y2 = box
    try:
        with Image.open(path) as src:
            logo = src.convert("RGBA")
            white = Image.new("RGBA", logo.size, "white")
            diff = ImageChops.difference(logo, white)
            bbox = diff.getbbox()
            if bbox:
                logo = logo.crop(bbox)
            logo.thumbnail((x2 - x1, y2 - y1), Image.Resampling.LANCZOS)
            px = x1 + ((x2 - x1) - logo.width) // 2
            py = y1 + ((y2 - y1) - logo.height) // 2
            canvas.paste(logo, (px, py), logo)
    except OSError:
        return


def draw_key_values(
    draw: ImageDraw.ImageDraw,
    items: list[tuple[str, str]],
    x: int,
    y: int,
    w: int,
    gap: int = 34,
    label_font=None,
    value_font=None,
) -> int:
    label_font = label_font or FONT["small_bold"]
    value_font = value_font or FONT["small_bold"]
    value_x = x + int(w * 0.43)
    value_width = max(40, x + w - value_x)
    for label, value in items:
        draw.text((x, y), label.upper(), fill=MUTED, font=label_font)
        draw.text((value_x, y), fit_text_to_width(draw, value or "-", value_font, value_width), fill=TEXT, font=value_font)
        y += gap
    return y


def draw_key_values_wrapped(
    draw: ImageDraw.ImageDraw,
    items: list[tuple[str, str]],
    x: int,
    y: int,
    w: int,
    label_ratio: float = 0.37,
    row_gap: int = 10,
    max_bottom: int | None = None,
    label_font=None,
    value_font=None,
) -> int:
    label_font = label_font or FONT["small_bold"]
    value_font = value_font or FONT["small_bold"]
    value_x = x + int(w * label_ratio)
    value_width = max(40, w - int(w * label_ratio))
    for label, value in items:
        if max_bottom is not None and y + text_height(draw, label, label_font) > max_bottom:
            break
        row_y = y
        draw.text((x, row_y), label.upper(), fill=MUTED, font=label_font)
        remaining_lines = None
        if max_bottom is not None:
            line_height = text_height(draw, "Ag", value_font) + 2
            remaining_lines = max(1, (max_bottom - row_y) // max(1, line_height))
        value_bottom = draw_text(
            draw,
            (value_x, row_y),
            value or "-",
            TEXT,
            value_font,
            max_width=value_width,
            line_gap=2,
            max_lines=remaining_lines,
        )
        label_bottom = row_y + text_height(draw, label, label_font)
        y = max(label_bottom, value_bottom) + row_gap
    return y


def risk_color(risk_level: str) -> str:
    risk = risk_level.upper()
    if risk == "HIGH":
        return RED
    if risk in {"MODERATE", "MEDIUM"}:
        return YELLOW
    return GREEN


def condition_label_for_score(score: int) -> str:
    if score >= 80:
        return "GOOD"
    if score >= 60:
        return "FAIR"
    return "POOR"


def risk_level_for_score(score: int) -> str:
    if score >= 80:
        return "LOW"
    if score >= 60:
        return "MODERATE"
    return "HIGH"


def clamp_score(value: object, default: int = 0) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return default


def visual_risk_factors_from_text(analysis: dict) -> dict:
    factors = dict(analysis.get("visual_risk_factors") or {})
    notes = factors.get("notes")
    if not isinstance(notes, list):
        notes = []

    text = " ".join(
        [normalize_text(analysis.get("summary")), normalize_text(analysis.get("recommendation"))]
        + [normalize_text(item) for item in analysis.get("observations") or []]
    ).lower()

    if not isinstance(factors.get("dark_staining_or_discoloration"), bool) and any(
        term in text for term in ("dark stain", "darkened", "discolor", "uneven color", "staining", "mottled")
    ):
        factors["dark_staining_or_discoloration"] = True
    if not isinstance(factors.get("suspected_ponding"), bool) and any(
        term in text for term in ("ponding", "standing water", "poor drainage", "water retention")
    ):
        factors["suspected_ponding"] = True
    if not isinstance(factors.get("high_penetration_density"), bool) and any(
        term in text for term in ("many penetration", "numerous penetration", "skylight", "vent", "rooftop unit", "rtu", "curb")
    ):
        factors["high_penetration_density"] = True
    if not isinstance(factors.get("overhanging_trees_or_debris"), bool) and any(
        term in text for term in ("overhanging tree", "tree overhang", "debris", "leaf", "branches")
    ):
        factors["overhanging_trees_or_debris"] = True

    factors.setdefault("dark_staining_or_discoloration", False)
    factors.setdefault("suspected_ponding", False)
    factors.setdefault("high_penetration_density", False)
    factors.setdefault("overhanging_trees_or_debris", False)
    factors["notes"] = [normalize_text(note) for note in notes if normalize_text(note)][:4]
    return factors


def apply_visual_risk_adjustment(analysis: dict) -> dict:
    adjusted = dict(analysis)
    factors = visual_risk_factors_from_text(adjusted)
    adjusted["visual_risk_factors"] = factors
    breakdown = dict(adjusted.get("breakdown") or {})
    adjusted["breakdown"] = breakdown

    active_labels: list[str] = []
    score_cap = 100
    if factors.get("dark_staining_or_discoloration"):
        active_labels.append("dark staining or inconsistent roof color")
        score_cap = min(score_cap, 72)
        breakdown["Membrane Condition"] = min(clamp_score(breakdown.get("Membrane Condition"), 72), 68)
        breakdown["Overall Maintenance"] = min(clamp_score(breakdown.get("Overall Maintenance"), 72), 68)
    if factors.get("suspected_ponding"):
        active_labels.append("possible ponding or drainage stress")
        score_cap = min(score_cap, 68)
        breakdown["Ponding"] = min(clamp_score(breakdown.get("Ponding"), 65), 55)
        breakdown["Membrane Condition"] = min(clamp_score(breakdown.get("Membrane Condition"), 65), 65)
    if factors.get("dark_staining_or_discoloration") and factors.get("suspected_ponding"):
        score_cap = min(score_cap, 62)
    if factors.get("high_penetration_density"):
        active_labels.append("high penetration or rooftop-unit density")
        score_cap = min(score_cap, 74)
        breakdown["Penetrations"] = min(clamp_score(breakdown.get("Penetrations"), 62), 58)
        breakdown["Flashing & Seals"] = min(clamp_score(breakdown.get("Flashing & Seals"), 66), 64)
    if factors.get("overhanging_trees_or_debris"):
        active_labels.append("tree overhang or roof debris exposure")
        score_cap = min(score_cap, 76)
        breakdown["Overall Maintenance"] = min(clamp_score(breakdown.get("Overall Maintenance"), 66), 62)
        breakdown["Membrane Condition"] = min(clamp_score(breakdown.get("Membrane Condition"), 70), 68)

    if not active_labels:
        return adjusted

    original_score = clamp_score(adjusted.get("overall_score"), 0)
    adjusted_score = min(original_score, score_cap)
    adjusted["visual_risk_score_cap"] = score_cap
    adjusted["overall_score"] = adjusted_score
    adjusted["condition_label"] = condition_label_for_score(adjusted_score)
    adjusted["risk_level"] = risk_level_for_score(adjusted_score)

    concern_text = "Visible risk factors include " + ", ".join(active_labels) + "."
    observations = [normalize_text(item) for item in adjusted.get("observations") or [] if normalize_text(item)]
    if not any(label in " ".join(observations).lower() for label in active_labels):
        observations.insert(0, concern_text)
    adjusted["observations"] = observations[:5]

    summary = normalize_text(adjusted.get("summary"))
    if concern_text.lower() not in summary.lower():
        adjusted["summary"] = normalize_text(f"{summary} {concern_text}")

    recommendation = normalize_text(adjusted.get("recommendation"))
    if "field inspection" not in recommendation.lower():
        adjusted["recommendation"] = normalize_text(
            f"{recommendation} Field inspection should verify drainage, moisture, penetrations, flashing, and debris-related damage."
        )
    return adjusted


def align_summary_with_adjusted_condition(summary: str, label: str, risk: str) -> str:
    text = normalize_text(summary)
    if not text:
        return text
    label_text = label.lower()
    risk_text = risk.lower()
    for condition in ("good", "fair", "poor"):
        text = text.replace(f"in {condition} condition", f"in {label_text} current-likely condition")
        text = text.replace(f"in generally {condition} condition", f"in {label_text} current-likely condition")
    for risk_level in ("low", "moderate", "medium", "high"):
        text = text.replace(f"Overall risk is {risk_level}", f"Overall risk is {risk_text}")
        text = text.replace(f"overall risk is {risk_level}", f"overall risk is {risk_text}")
    return text


def apply_aerial_age_adjustment(row: dict, analysis: dict) -> dict:
    if analysis.get("aerial_age_adjustment_applied"):
        return analysis

    adjusted = dict(analysis)
    breakdown = dict(adjusted.get("breakdown") or {})
    adjusted["breakdown"] = breakdown

    image_age_years = aerial_photo_age_years(row)
    if image_age_years < 2:
        adjusted["aerial_age_adjustment_applied"] = False
        adjusted["aerial_photo_age_years"] = round(image_age_years, 1)
        adjusted["aerial_age_score_adjustment"] = 0
        return adjusted

    score_adjustment = min(15, int(round(image_age_years)))
    original_score = int(adjusted.get("overall_score") or 0)
    adjusted_score = max(0, min(100, original_score - score_adjustment))
    adjusted["original_overall_score"] = original_score
    adjusted["overall_score"] = adjusted_score
    adjusted["condition_label"] = condition_label_for_score(adjusted_score)
    adjusted["risk_level"] = risk_level_for_score(adjusted_score)
    adjusted["summary"] = align_summary_with_adjusted_condition(
        normalize_text(adjusted.get("summary")),
        adjusted["condition_label"],
        adjusted["risk_level"],
    )
    adjusted["aerial_age_adjustment_applied"] = True
    adjusted["aerial_photo_age_years"] = round(image_age_years, 1)
    adjusted["aerial_age_score_adjustment"] = score_adjustment

    for key, value in list(breakdown.items()):
        try:
            breakdown[key] = max(0, min(100, int(value) - score_adjustment))
        except (TypeError, ValueError):
            continue

    return adjusted


def coating_recommendation(analysis: dict) -> str:
    score = int(analysis.get("overall_score") or 0)
    risk = normalize_text(analysis.get("risk_level")).upper()
    breakdown = analysis.get("breakdown") or {}
    membrane = int(breakdown.get("Membrane Condition") or score)
    ponding = int(breakdown.get("Ponding") or score)
    flashing = int(breakdown.get("Flashing & Seals") or score)
    observations = " ".join(normalize_text(item) for item in analysis.get("observations") or []).lower()
    concern_terms = (
        "ponding",
        "open tear",
        "missing",
        "collapse",
        "widespread",
        "severe",
        "active leak",
        "trapped moisture",
        "saturated",
    )
    visible_concerns = any(term in observations for term in concern_terms)

    if risk == "HIGH" or score < 60 or membrane < 60 or ponding < 55 or flashing < 55:
        return (
            "Roof coating is not recommended from the aerial analysis alone. The observed condition indicates "
            "that field inspection should first confirm membrane integrity, moisture conditions, seams, flashing, "
            "and whether repair or replacement is more appropriate."
        )
    if score >= 72 and membrane >= 70 and ponding >= 65 and flashing >= 65 and not visible_concerns:
        return (
            "A silicone roof coating appears to be a reasonable restoration option based on the observed conditions, "
            "provided a field inspection confirms the roof is dry, structurally sound, well-adhered, and free of "
            "active leaks or trapped moisture."
        )
    return (
        "A silicone roof coating may be viable, but it should be treated as conditional until field inspection "
        "verifies membrane adhesion, moisture content, seams, penetrations, flashing, and drainage performance."
    )


def risk_meter_value(score: int, risk_level: str) -> int:
    risk = risk_level.upper()
    score = max(0, min(100, int(score)))

    def interpolate(value: int, in_low: int, in_high: int, out_low: int, out_high: int) -> float:
        if in_high == in_low:
            return float(out_low)
        pct = (value - in_low) / (in_high - in_low)
        return out_low + pct * (out_high - out_low)

    def clamp_meter(value: float, low: int, high: int) -> int:
        return int(round(max(low, min(high, value))))

    if risk == "LOW":
        return clamp_meter(interpolate(score, 80, 100, 33, 0), 0, 33)
    if risk in {"MODERATE", "MEDIUM"}:
        return clamp_meter(interpolate(score, 55, 79, 66, 34), 34, 66)
    if risk == "HIGH":
        return clamp_meter(interpolate(score, 0, 54, 100, 67), 67, 100)
    return clamp_meter(100 - score, 0, 100)


def draw_risk_meter(draw: ImageDraw.ImageDraw, score: int, risk_level: str, box: tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = box
    cx = (x1 + x2) // 2
    cy = y2 - 28
    radius = min((x2 - x1) // 2 - 10, y2 - y1 - 34)
    width = 13

    def arc_points(start: int, end: int) -> list[tuple[int, int]]:
        step = -3 if start > end else 3
        angles = list(range(start, end + step, step))
        return [
            (
                cx + int(cos(radians(angle)) * radius),
                cy - int(sin(radians(angle)) * radius),
            )
            for angle in angles
        ]

    draw.line(arc_points(180, 120), fill=GREEN, width=width, joint="curve")
    draw.line(arc_points(120, 60), fill=YELLOW, width=width, joint="curve")
    draw.line(arc_points(60, 0), fill=RED, width=width, joint="curve")

    risk_value = risk_meter_value(score, risk_level)
    angle = 180 - (risk_value * 1.8)
    needle_len = radius - 18
    end_x = cx + int(cos(radians(angle)) * needle_len)
    end_y = cy - int(sin(radians(angle)) * needle_len)
    draw.line((cx, cy, end_x, end_y), fill="#3f3f46", width=5)
    draw.ellipse((cx - 11, cy - 11, cx + 11, cy + 11), fill="#55555a")
    draw.text((x1 + 4, y2 - 12), "Lower Risk", fill=TEXT, font=FONT["small"])
    draw.text((x2 - 90, y2 - 12), "Higher Risk", fill=TEXT, font=FONT["small"])


def draw_score_card(draw: ImageDraw.ImageDraw, analysis: dict, box: tuple[int, int, int, int]) -> None:
    card(draw, box)
    x1, y1, x2, _ = box
    score = int(analysis.get("overall_score") or 0)
    label = normalize_text(analysis.get("condition_label")) or "UNKNOWN"
    risk = normalize_text(analysis.get("risk_level")).upper() or "MODERATE"
    color = risk_color(risk)
    draw.text((x1 + 28, y1 + 18), "OVERALL ROOF CONDITION SCORE", fill=TEXT, font=FONT["small_bold"])
    draw.text((x1 + 95, y1 + 60), str(score), fill=color, font=FONT["score"])
    draw.text((x1 + 210, y1 + 122), "/100", fill=TEXT, font=FONT["score_small"])
    draw.text((x1 + 128, y1 + 172), label.upper(), fill=TEXT, font=FONT["subtitle"])
    draw.text((x2 - 180, y1 + 18), "RISK LEVEL", fill=TEXT, font=FONT["small_bold"])
    draw.text((x2 - 170, y1 + 48), risk, fill=color, font=FONT["section"])
    draw_risk_meter(draw, score, risk, (x2 - 205, y1 + 96, x2 - 28, y1 + 205))


def draw_breakdown(draw: ImageDraw.ImageDraw, analysis: dict, box: tuple[int, int, int, int]) -> None:
    card(draw, box, "Roof Condition Breakdown")
    x1, y1, x2, _ = box
    y = y1 + 62
    breakdown = analysis.get("breakdown") or {}
    defaults = ["Membrane Condition", "Ponding", "Flashing & Seals", "Penetrations", "Overall Maintenance"]
    for key in defaults:
        value = int(breakdown.get(key, analysis.get("overall_score") or 0))
        draw.text((x1 + 20, y), key, fill=TEXT, font=FONT["small_bold"])
        bx = x1 + 245
        by = y + 4
        draw.rectangle((bx, by, bx + 240, by + 13), fill="#e5e7eb")
        draw.rectangle((bx, by, bx + int(240 * max(0, min(100, value)) / 100), by + 13), fill=BLUE)
        draw.text((x2 - 90, y - 2), f"{value}/100", fill=TEXT, font=FONT["small_bold"])
        y += 42


def image_dimensions(path: Path | None) -> tuple[int, int]:
    if not path or not path.exists():
        return 0, 0
    try:
        with Image.open(path) as img:
            return img.size
    except OSError:
        return 0, 0


def replacement_confidence_inputs(row: dict, analysis: dict, denver_path: Path | None) -> CostConfidenceInputs:
    width, height = image_dimensions(denver_path)
    max_side = max(width, height)
    analysis_text = " ".join(
        [
            normalize_text(analysis.get("roof_type")),
            normalize_text(analysis.get("roof_system")),
            normalize_text(analysis.get("summary")),
            normalize_text(analysis.get("recommendation")),
            " ".join(normalize_text(item) for item in analysis.get("observations") or []),
        ]
    ).lower()
    roof_type = normalize_text(analysis.get("roof_type")).lower()
    roof_system = normalize_text(analysis.get("roof_system")).lower()
    uncertain_terms = ("unknown", "likely", "not verifiable", "cannot be confirmed", "cannot confirm")

    return CostConfidenceInputs(
        roof_type_confidently_identified=bool(roof_type or roof_system)
        and not any(term in f"{roof_type} {roof_system}" for term in uncertain_terms),
        roof_area_accurately_measured=int_value(row.get("Building Footprint Sq Ft")) > 0,
        building_footprint_available=bool(normalize_text(row.get("Building Footprint"))),
        high_resolution_imagery_available=max_side >= 1000,
        shadows_obscure_roof="shadow" in analysis_text and any(term in analysis_text for term in ("obscure", "obscures", "obscured")),
        tree_coverage_obscures_roof="tree" in analysis_text and any(term in analysis_text for term in ("obscure", "obscures", "obscured")),
        image_resolution_poor=max_side > 0 and max_side < 400 or "poor resolution" in analysis_text or "low resolution" in analysis_text,
        roof_edges_hidden=("edge" in analysis_text or "edges" in analysis_text)
        and any(term in analysis_text for term in ("hidden", "obscure", "obscures", "obscured")),
    )


def draw_replacement_cost_estimate(
    draw: ImageDraw.ImageDraw,
    row: dict,
    analysis: dict,
    denver_path: Path | None,
    box: tuple[int, int, int, int],
) -> None:
    card(draw, box, "Roof Replacement Cost Estimate")
    x1, y1, x2, _ = box
    estimate = estimate_roof_replacement_cost(
        roof_condition_score=float(analysis.get("overall_score") or 0),
        roof_area_sqft=float(int_value(row.get("Building Footprint Sq Ft"))),
        confidence_inputs=replacement_confidence_inputs(row, analysis, denver_path),
    )

    draw.text((x1 + 22, y1 + 62), "TOTAL PROJECT COST", fill=MUTED, font=FONT["small_bold"])
    draw.text((x1 + 22, y1 + 92), format_currency(estimate.total_project_cost), fill="#177a28", font=FONT["total_cost"])
    draw.text((x1 + 22, y1 + 150), f"${estimate.cost_per_sqft:,.2f} / SF", fill=TEXT, font=FONT["body_bold"])

    label_x = x1 + 420
    value_x = x2 - 190
    y = y1 + 58
    draw.text((label_x, y), "COST COMPONENT", fill=MUTED, font=FONT["small_bold"])
    draw.text((value_x, y), "COST", fill=MUTED, font=FONT["small_bold"])
    y += 28

    for label, value in estimate.component_costs.items():
        draw.text((label_x, y), label, fill=TEXT, font=FONT["body"])
        draw.text((value_x, y), format_currency(value), fill=TEXT, font=FONT["body_bold"])
        y += 28

    draw.line((label_x, y + 4, x2 - 24, y + 4), fill=LIGHT, width=2)
    y += 18
    summary_rows = [
        ("Replacement Subtotal", estimate.replacement_subtotal),
        ("Contingency (15%)", estimate.contingency_cost),
        ("Total Project Cost", estimate.total_project_cost),
    ]
    for label, value in summary_rows:
        value_font = FONT["body_bold"]
        value_fill = "#177a28" if label == "Total Project Cost" else TEXT
        draw.text((label_x, y), label, fill=TEXT, font=FONT["body_bold"])
        draw.text((value_x, y), format_currency(value), fill=value_fill, font=value_font)
        y += 26

    disclaimer = (
        "This replacement cost is an estimate derived from aerial imagery, public property "
        "records, and commercial roofing cost models. It is intended for budgeting purposes only and "
        "should not be considered a contractor quote or engineering assessment."
    )
    draw_text(draw, (x1 + 22, y + 22), disclaimer, MUTED, FONT["small"], max_width=x2 - x1 - 44, line_gap=1)


def draw_overlay_cost_estimate(
    draw: ImageDraw.ImageDraw,
    row: dict,
    analysis: dict,
    denver_path: Path | None,
    box: tuple[int, int, int, int],
) -> None:
    card(draw, box, "Roof Overlay Cost Estimate")
    x1, y1, x2, _ = box
    estimate = estimate_roof_replacement_cost(
        roof_condition_score=float(analysis.get("overall_score") or 0),
        roof_area_sqft=float(int_value(row.get("Building Footprint Sq Ft"))),
        confidence_inputs=replacement_confidence_inputs(row, analysis, denver_path),
    )

    draw.text((x1 + 22, y1 + 58), "TOTAL PROJECT COST", fill=MUTED, font=FONT["small_bold"])
    draw.text((x1 + 22, y1 + 86), format_currency(estimate.overlay_total_project_cost), fill="#177a28", font=FONT["total_cost"])
    draw.text((x1 + 22, y1 + 128), f"${estimate.overlay_cost_per_sqft:,.2f} / SF", fill=TEXT, font=FONT["body_bold"])

    label_x = x1 + 420
    value_x = x2 - 190
    y = y1 + 58
    draw.text((label_x, y), "COST COMPONENT", fill=MUTED, font=FONT["small_bold"])
    draw.text((value_x, y), "COST", fill=MUTED, font=FONT["small_bold"])
    y += 28
    summary_rows = [
        ("Overlay Subtotal", estimate.overlay_subtotal),
        ("Contingency (10%)", estimate.overlay_contingency_cost),
        ("Total Project Cost", estimate.overlay_total_project_cost),
    ]
    for label, value in summary_rows:
        value_fill = "#177a28" if label == "Total Project Cost" else TEXT
        draw.text((label_x, y), label, fill=TEXT, font=FONT["body_bold"])
        draw.text((value_x, y), format_currency(value), fill=value_fill, font=FONT["body_bold"])
        y += 26

    disclaimer = (
        "This overlay cost is an estimate derived from aerial imagery, public property "
        "records, and commercial roofing cost models. It is intended for budgeting purposes only and "
        "should not be considered a contractor quote or engineering assessment."
    )
    draw_text(draw, (x1 + 22, y1 + 162), disclaimer, MUTED, FONT["small"], max_width=x2 - x1 - 44, line_gap=1)


def format_land_area(value: object) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    try:
        acres = float(text.replace(",", ""))
    except ValueError:
        return text
    return f"{acres:,.2f} acres"


def draw_building_characteristics(draw: ImageDraw.ImageDraw, row: dict, box: tuple[int, int, int, int]) -> None:
    card(draw, box, "Building Characteristics")
    x1, y1, x2, _ = box
    draw_key_values(
        draw,
        [
            ("Land Area", format_land_area(row.get("Land Area"))),
            ("Stories", normalize_text(row.get("Stories"))),
            ("Construction Type", normalize_text(row.get("Construction Type"))),
            ("Tax District", normalize_text(row.get("Tax District"))),
            ("Land Value", format_currency(row.get("Land Value")) if normalize_text(row.get("Land Value")) else ""),
        ],
        x1 + 22,
        y1 + 62,
        x2 - x1 - 44,
        gap=24,
        label_font=FONT["small_bold"],
        value_font=FONT["small_bold"],
    )


def possible_roof_systems_text(analysis: dict) -> str:
    systems = analysis.get("possible_roof_systems") or []
    if not isinstance(systems, list):
        return ""
    parts: list[str] = []
    for item in systems[:3]:
        if not isinstance(item, dict):
            continue
        system = normalize_text(item.get("system"))
        if not system:
            continue
        confidence = item.get("confidence")
        try:
            confidence_text = f" ({int(confidence)}%)"
        except (TypeError, ValueError):
            confidence_text = ""
        parts.append(system + confidence_text)
    return "; ".join(parts)


def visible_concerns_text(analysis: dict) -> str:
    factors = visual_risk_factors_from_text(analysis)
    concerns: list[str] = []
    if factors.get("dark_staining_or_discoloration"):
        concerns.append("dark staining/color variation")
    if factors.get("suspected_ponding"):
        concerns.append("possible ponding")
    if factors.get("high_penetration_density"):
        concerns.append("many penetrations/units")
    if factors.get("overhanging_trees_or_debris"):
        concerns.append("tree/debris exposure")
    notes = [normalize_text(note) for note in factors.get("notes") or [] if normalize_text(note)]
    if notes and len(concerns) < 3:
        concerns.extend(notes[: 3 - len(concerns)])
    return "; ".join(concerns[:4]) or "None prominent from aerial image"


def render_report(row: dict, analysis: dict, denver_path: Path | None, drcog_path: Path | None, output_path: Path) -> None:
    main_source, main_path = aerial_source_label(row), denver_path

    canvas = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, PAGE_W - 1, PAGE_H - 1), outline="#9ca3af", width=2)

    logo_path = Path(os.environ.get("PCS_LOGO_PATH", DEFAULT_PCS_LOGO_PATH))
    paste_logo_fit(canvas, logo_path, (MARGIN, 28, 320, 150))
    draw.text((500, 42), "ROOF INTELLIGENCE REPORT", fill="black", font=FONT["title"])
    draw.text((640, 96), "POWERED BY PILOTPOINT IQ", fill=DARK_BLUE, font=FONT["section"])
    draw.text((1450, 46), "REPORT DATE:", fill=TEXT, font=FONT["small_bold"])
    draw.text((1450, 72), date.today().strftime("%b %d, %Y"), fill=TEXT, font=FONT["small"])
    draw.text((1450, 110), "REPORT ID:", fill=TEXT, font=FONT["small_bold"])
    draw.text((1450, 136), report_id(row), fill=TEXT, font=FONT["small"])

    property_card = (MARGIN, 205, 1655, 370)
    card(draw, property_card)
    prop_x, prop_y = MARGIN + 22, 225
    draw.text(
        (prop_x, prop_y),
        fit_text_to_width(draw, normalize_text(row.get("Address")) or "Unknown Address", FONT["brand"], property_card[2] - prop_x - 24),
        fill="black",
        font=FONT["brand"],
    )
    location = " ".join(part for part in [row.get("Building City"), row.get("Building State"), row.get("Building ZIP")] if part)
    draw.text((prop_x, prop_y + 56), fit_text_to_width(draw, location, FONT["subtitle"], property_card[2] - prop_x - 24), fill=TEXT, font=FONT["subtitle"])

    metric_y = 318
    for x, label, value in [
        (64, "Property Type", shorten(row.get("Property Use"), 38)),
        (505, "Year Built", normalize_text(row.get("Year Built"))),
        (665, "Building Area", f"{format_int(row.get('Building Footprint Sq Ft'))} SF"),
        (930, "Roof Squares", f"{roof_squares(row):,}"),
        (1120, "Parcel ID", normalize_text(row.get("Parcel Number"))),
    ]:
        draw.text((x, metric_y), label.upper(), fill=MUTED, font=FONT["body_bold"])
        next_x = 1655
        if x == 64:
            next_x = 455
        elif x == 505:
            next_x = 640
        elif x == 665:
            next_x = 900
        elif x == 930:
            next_x = 1090
        draw.text((x, metric_y + 25), fit_text_to_width(draw, value or "-", FONT["body_bold"], next_x - x - 18), fill=TEXT, font=FONT["body_bold"])

    paste_fit(canvas, main_path, (MARGIN, 390, 972, 1020))
    aerial_date = format_aerial_photo_date(aerial_photo_date_value(row))
    aerial_label = f"SELECTED AERIAL IMAGE - {main_source.upper()}"
    if aerial_date:
        aerial_label += f" AS OF {aerial_date}"
    draw.text((MARGIN, 1035), aerial_label, fill=BLUE, font=FONT["section"])
    draw_score_card(draw, analysis, (1000, 390, 1655, 685))

    card(draw, (1000, 705, 1655, 1050), "Roof Information")
    draw_key_values_wrapped(
        draw,
        [
            ("Roof Type", normalize_text(analysis.get("roof_type"))),
            ("Roof System", normalize_text(analysis.get("roof_system"))),
            ("Possible Types", possible_roof_systems_text(analysis)),
            ("Visible Concerns", visible_concerns_text(analysis)),
            ("Roof Age Est.", normalize_text(analysis.get("roof_age_estimate"))),
            ("Roof Area", f"{format_int(row.get('Building Footprint Sq Ft'))} SF"),
            ("Roof Pitch", normalize_text(analysis.get("roof_pitch"))),
            ("Confidence", f"{analysis.get('ai_confidence', 0)}%" if analysis.get("source") in {"openai", "gemini"} else "Pending AI"),
        ],
        1022,
        763,
        600,
        label_ratio=0.31,
        row_gap=10,
        max_bottom=1034,
    )

    card(draw, (MARGIN, 1070, 642, 1380), "Roof Condition Breakdown")
    draw_breakdown(draw, analysis, (MARGIN, 1070, 642, 1380))

    card(draw, (675, 1070, 1655, 1380), "Aerial Roof Observations")
    y = 1135
    for idx, observation in enumerate((analysis.get("observations") or [])[:5], start=1):
        item_top = y
        text_bottom = draw_text(draw, (697, y - 4), f"{idx}. {observation}", TEXT, FONT["body"], max_width=910, line_gap=2)
        y = max(item_top + 38, text_bottom + 12)

    lower_left_x2 = 805
    lower_right_x1 = 835
    lower_left_text_width = lower_left_x2 - MARGIN - 44

    draw_building_characteristics(draw, row, (MARGIN, 1400, lower_left_x2, 1593))

    card(draw, (MARGIN, 1613, lower_left_x2, 2075), "Report Summary")
    y = draw_text(draw, (MARGIN + 22, 1678), normalize_text(analysis.get("summary")), TEXT, FONT["body"], max_width=lower_left_text_width, line_gap=6)
    draw.text((MARGIN + 22, y + 12), "Recommendation:", fill=TEXT, font=FONT["body_bold"])
    draw_text(draw, (MARGIN + 22, y + 44), normalize_text(analysis.get("recommendation")), TEXT, FONT["body"], max_width=lower_left_text_width, line_gap=6)

    draw_replacement_cost_estimate(draw, row, analysis, denver_path, (lower_right_x1, 1400, 1655, 1825))
    draw_overlay_cost_estimate(draw, row, analysis, denver_path, (lower_right_x1, 1845, 1655, 2075))

    pilotpointiq_logo_path = Path(os.environ.get("PILOTPOINTIQ_LOGO_PATH", DEFAULT_PILOTPOINTIQ_LOGO_PATH))
    paste_logo_trimmed_fit(canvas, pilotpointiq_logo_path, (MARGIN, 2092, 230, 2160))
    draw.text(
        (250, 2117),
        "PilotPoint IQ a division of Booker Tech Solutions, LLC",
        fill=TEXT,
        font=FONT["footer"],
    )
    copyright_notice = "© PilotPoint IQ Roof Intelligence All rights reserved"
    draw.text(
        (PAGE_W - MARGIN - text_width(draw, copyright_notice, FONT["small"]), 2142),
        copyright_notice,
        fill=TEXT,
        font=FONT["small"],
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "PDF", resolution=200.0)


def read_rows(csv_path: Path) -> list[dict]:
    csv.field_size_limit(1024 * 1024 * 1024)
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def safe_path_part(value: object, fallback: str) -> str:
    text = normalize_text(value)
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", " ") else "-" for ch in text).strip()
    cleaned = "-".join(cleaned.split())
    return cleaned or fallback


def row_zip_code(row: dict) -> str:
    value = normalize_text(row.get("Building ZIP"))
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[:5] if digits else "Unknown-ZIP"


def row_output_dirs(root_dir: Path, row: dict) -> dict[str, Path]:
    state = safe_path_part(row.get("Building State"), "Unknown-State").upper()
    zip_code = row_zip_code(row)
    base = root_dir / state / zip_code
    dirs = {
        "base": base,
        "reports": base / "Reports",
        "aerial": base / "Aerial Imagery",
        "json": base / "json",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def row_county_name(row: dict) -> str:
    explicit = normalize_text(row.get("County"))
    if explicit:
        return safe_path_part(explicit.replace(" County", ""), "Unknown-County")

    source = aerial_source_label(row).lower()
    city = normalize_text(row.get("Building City")).lower()
    if "arapahoe" in source:
        return "Arapahoe"
    if "jefferson" in source:
        return "Jefferson"
    if city == "denver":
        return "Denver"
    return "Unknown-County"


def requested_county_name(value: object) -> str:
    text = normalize_text(value).replace(" County", "")
    return safe_path_part(text, "") if text else ""


def row_matches_requested_scope(row: dict, state: str, county: str, zip_code: str) -> tuple[bool, list[str]]:
    problems = []
    if state:
        row_state = safe_path_part(row.get("Building State"), "Unknown-State").upper()
        if row_state != state.upper():
            problems.append(f"state {row_state} != {state.upper()}")
    if county:
        row_county = row_county_name(row).lower()
        if row_county != county.lower():
            problems.append(f"county {row_county} != {county.lower()}")
    if zip_code:
        row_zip = row_zip_code(row)
        if row_zip != zip_code:
            problems.append(f"zip {row_zip} != {zip_code}")
    return not problems, problems


def apply_requested_scope_defaults(row: dict, state: str, county: str, zip_code: str) -> None:
    if state and not normalize_text(row.get("Building State")):
        row["Building State"] = state
    if county and not normalize_text(row.get("County")):
        row["County"] = county
    if zip_code and not normalize_text(row.get("Building ZIP")):
        row["Building ZIP"] = zip_code


def row_data_dirs(root_dir: Path, row: dict) -> dict[str, Path]:
    state = safe_path_part(row.get("Building State"), "Unknown-State").upper()
    county = row_county_name(row)
    base = root_dir / "data" / state / county
    dirs = {
        "base": base,
        "parcels": base / "parcels",
        "aerial": base / "aerial_imagery",
        "json": base / "json",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def safe_report_stem(row: dict, fallback: str) -> str:
    parcel = safe_path_part(row.get("Parcel Number"), fallback)
    address = safe_path_part(normalize_text(row.get("Address")).lower(), "roof-report")
    return f"{parcel}-{address}"


def organize_aerial_image(source_path: Path | None, aerial_dir: Path, row: dict, fallback: str) -> Path | None:
    if not source_path or not source_path.exists():
        return None
    suffix = source_path.suffix or ".jpg"
    destination = aerial_dir / f"{safe_report_stem(row, fallback)}-aerial{suffix}"
    try:
        if source_path.resolve() != destination.resolve():
            shutil.copy2(source_path, destination)
    except FileNotFoundError:
        shutil.copy2(source_path, destination)
    return destination


def remove_stale_parcel_files(directory: Path, parcel: str, keep: set[Path], suffixes: tuple[str, ...]) -> list[str]:
    if not parcel or not directory.exists():
        return []
    keep_resolved = {path.resolve() for path in keep if path}
    removed = []
    for candidate in directory.glob(f"{safe_path_part(parcel, parcel)}-*"):
        if not candidate.is_file() or candidate.suffix.lower() not in suffixes:
            continue
        try:
            if candidate.resolve() in keep_resolved:
                continue
            candidate.unlink()
            removed.append(str(candidate))
        except OSError as exc:
            removed.append(f"{candidate} (cleanup failed: {exc})")
    return removed


def cleanup_stale_outputs(
    dirs: dict[str, Path],
    data_dirs: dict[str, Path],
    row: dict,
    report_path: Path,
    deliverable_aerial_path: Path | None,
    data_aerial_path: Path | None,
) -> list[str]:
    parcel = normalize_text(row.get("Parcel Number"))
    if not parcel:
        return []
    removed = []
    removed.extend(remove_stale_parcel_files(dirs["reports"], parcel, {report_path}, (".pdf",)))
    removed.extend(remove_stale_parcel_files(dirs["aerial"], parcel, {deliverable_aerial_path} if deliverable_aerial_path else set(), (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff")))
    removed.extend(remove_stale_parcel_files(data_dirs["aerial"], parcel, {data_aerial_path} if data_aerial_path else set(), (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff")))
    return removed


def analysis_json_name(row: dict, analysis: dict, use_ai: bool, provider: str) -> str:
    parcel = normalize_text(row.get("Parcel Number")) or hashlib.sha1(json.dumps(row).encode("utf-8")).hexdigest()[:12]
    source = normalize_text(analysis.get("source")).lower()
    prefix = source if source in {"openai", "gemini"} else provider if use_ai and source == provider else "fallback"
    return f"{prefix}-{parcel}.json"


def write_analysis_json(row: dict, analysis: dict, json_dirs: tuple[Path, ...], use_ai: bool, provider: str) -> None:
    file_name = analysis_json_name(row, analysis, use_ai, provider)
    content = json.dumps(analysis, indent=2)
    for directory in json_dirs:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / file_name).write_text(content, encoding="utf-8")


def existing_analysis_source(row: dict, json_dirs: tuple[Path, ...], provider: str) -> str:
    parcel = normalize_text(row.get("Parcel Number"))
    if not parcel:
        return ""
    for directory in json_dirs:
        for prefix in (provider, "openai", "gemini", "fallback"):
            path = directory / f"{prefix}-{parcel}.json"
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            return normalize_text(data.get("source")).lower() or prefix
    return ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate one-page roof intelligence PDF reports.")
    parser.add_argument(
        "--input",
        default="data/CO/Denver/parcels/denver_buildings_with_parcels_80223_with_aerial.csv",
        help="Building with parcel CSV",
    )
    parser.add_argument("--output-dir", default=".", help="Root directory for State/ZIP organized report output")
    parser.add_argument("--analysis-cache-dir", default=None, help="Deprecated; JSON now writes under each State/ZIP/json folder")
    parser.add_argument("--state", default=None, help="Validate rows against this state code")
    parser.add_argument("--county", default=None, help="Validate rows against this county name")
    parser.add_argument("--zip-code", default=None, help="Validate rows against this ZIP code")
    parser.add_argument("--limit", type=int, default=None, help="Maximum reports to generate")
    parser.add_argument("--start", type=int, default=0, help="Zero-based row offset")
    parser.add_argument("--use-ai", action="store_true", help="Call AI vision analysis when the selected provider API key is available")
    parser.add_argument("--ai-provider", choices=("openai", "gemini"), default="openai", help="AI provider for roof image analysis")
    parser.add_argument("--ai-model", default=None, help="Provider model for image analysis; defaults by provider")
    parser.add_argument("--allow-ai-fallback", action="store_true", help="Generate fallback reports if the selected AI provider fails")
    parser.add_argument("--skip-existing-reports", action="store_true", help="Skip rows whose target PDF already exists")
    parser.add_argument("--only-missing", action="store_true", help="Alias for --skip-existing-reports")
    parser.add_argument("--retry-failed-ai", action="store_true", help="With --use-ai, rerun rows whose existing analysis is fallback")
    parser.add_argument("--force", action="store_true", help="Replace existing output files; this is the default behavior")
    parser.add_argument("--cleanup-stale-only", action="store_true", help="Only remove stale parcel-scoped duplicate files; do not regenerate reports")
    parser.add_argument("--manifest", default=None, help="Write a JSON run manifest to this path")
    return parser.parse_args()


def default_ai_model(provider: str) -> str:
    if provider == "gemini":
        return os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    return os.environ.get("OPENAI_VISION_MODEL", "gpt-5.4-mini")


def main() -> int:
    base_dir = Path.cwd()
    script_dir = Path(__file__).resolve().parent
    load_env_file(script_dir / ".env")
    if base_dir != script_dir:
        load_env_file(base_dir / ".env")

    args = parse_args()
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = base_dir / input_path
    rows = read_rows(input_path)
    selected_rows = rows[args.start :]
    if args.limit is not None:
        selected_rows = selected_rows[: args.limit]

    requested_state = normalize_text(args.state).upper()
    requested_county = requested_county_name(args.county)
    requested_zip = "".join(ch for ch in normalize_text(args.zip_code) if ch.isdigit())[:5]

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = base_dir / output_dir
    ai_model = args.ai_model or default_ai_model(args.ai_provider)
    if args.use_ai:
        api_key_name = "GEMINI_API_KEY" if args.ai_provider == "gemini" else "OPENAI_API_KEY"
        if not os.environ.get(api_key_name):
            raise RuntimeError(f"--use-ai requested, but {api_key_name} is not set")

    manifest = {
        "input": str(input_path),
        "output_dir": str(output_dir),
        "state": requested_state,
        "county": requested_county,
        "zip_code": requested_zip,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "ai": {
            "requested": bool(args.use_ai),
            "provider": args.ai_provider,
            "model": ai_model,
            "allow_fallback": bool(args.allow_ai_fallback),
        },
        "counts": {
            "rows_selected": len(selected_rows),
            "generated": 0,
            "skipped_existing": 0,
            "preflight_failed": 0,
            "failed": 0,
            "ai": 0,
            "fallback": 0,
            "blank_or_missing_images": 0,
            "stale_files_removed": 0,
            "cleanup_only": 0,
        },
        "records": [],
    }

    for index, row in enumerate(selected_rows, start=args.start + 1):
        apply_requested_scope_defaults(row, requested_state, requested_county, requested_zip)
        parcel = normalize_text(row.get("Parcel Number")) or f"row-{index}"
        denver_path = resolve_path(base_dir, aerial_image_file_value(row))
        drcog_path = None
        dirs = row_output_dirs(output_dir, row)
        data_dirs = row_data_dirs(output_dir, row)
        output_path = dirs["reports"] / f"{safe_report_stem(row, f'row-{index}')}.pdf"
        record_status = {
            "row": index,
            "parcel": parcel,
            "address": normalize_text(row.get("Address")),
            "state": safe_path_part(row.get("Building State"), "Unknown-State").upper(),
            "county": row_county_name(row),
            "zip_code": row_zip_code(row),
            "report": str(output_path),
            "status": "pending",
            "problems": [],
        }

        matches_scope, scope_problems = row_matches_requested_scope(row, requested_state, requested_county, requested_zip)
        if not matches_scope:
            record_status["status"] = "preflight_failed"
            record_status["problems"] = scope_problems
            manifest["counts"]["preflight_failed"] += 1
            manifest["records"].append(record_status)
            print(f"Skipping {parcel}: {'; '.join(scope_problems)}")
            continue

        should_skip_existing = (args.skip_existing_reports or args.only_missing) and output_path.exists() and not args.force
        if should_skip_existing and args.retry_failed_ai and args.use_ai:
            prior_source = existing_analysis_source(row, (data_dirs["json"], dirs["json"]), args.ai_provider)
            should_skip_existing = prior_source in {"openai", "gemini"}
            record_status["prior_analysis_source"] = prior_source

        if should_skip_existing:
            record_status["status"] = "skipped_existing"
            manifest["counts"]["skipped_existing"] += 1
            manifest["records"].append(record_status)
            print(f"Skipping existing {output_path}")
            continue

        image_info = image_diagnostics(denver_path)
        record_status["image"] = image_info
        if image_info["blank"]:
            manifest["counts"]["blank_or_missing_images"] += 1
            problem = f"aerial image {image_info['reason']}"
            record_status["problems"].append(problem)
            if args.use_ai and not args.allow_ai_fallback:
                record_status["status"] = "preflight_failed"
                manifest["counts"]["preflight_failed"] += 1
                manifest["records"].append(record_status)
                print(f"Skipping {parcel}: {problem}")
                continue

        if args.cleanup_stale_only:
            data_denver_path = organize_aerial_image(denver_path, data_dirs["aerial"], row, f"row-{index}") or denver_path
            organized_denver_path = organize_aerial_image(data_denver_path, dirs["aerial"], row, f"row-{index}")
            removed_stale = cleanup_stale_outputs(dirs, data_dirs, row, output_path, organized_denver_path, data_denver_path)
            record_status["status"] = "cleanup_only"
            if removed_stale:
                record_status["stale_files_removed"] = removed_stale
                manifest["counts"]["stale_files_removed"] += len(removed_stale)
            manifest["counts"]["cleanup_only"] += 1
            manifest["records"].append(record_status)
            continue

        try:
            data_denver_path = organize_aerial_image(denver_path, data_dirs["aerial"], row, f"row-{index}") or denver_path
            organized_denver_path = organize_aerial_image(data_denver_path, dirs["aerial"], row, f"row-{index}")
            denver_path = organized_denver_path or denver_path
            removed_stale = cleanup_stale_outputs(dirs, data_dirs, row, output_path, organized_denver_path, data_denver_path)
            if removed_stale:
                record_status["stale_files_removed"] = removed_stale
                manifest["counts"]["stale_files_removed"] += len(removed_stale)
            analysis = load_or_create_analysis(
                row,
                denver_path,
                drcog_path,
                data_dirs["json"],
                args.use_ai and not image_info["blank"],
                args.ai_provider,
                ai_model,
                args.allow_ai_fallback,
            )
            analysis = apply_visual_risk_adjustment(analysis)
            analysis = apply_aerial_age_adjustment(row, analysis)
            write_analysis_json(row, analysis, (data_dirs["json"], dirs["json"]), args.use_ai, args.ai_provider)
            render_report(row, analysis, denver_path, drcog_path, output_path)
            source = normalize_text(analysis.get("source")).lower()
            record_status["status"] = "generated"
            record_status["analysis_source"] = source or "unknown"
            record_status["report"] = str(output_path)
            manifest["counts"]["generated"] += 1
            if source in {"openai", "gemini"}:
                manifest["counts"]["ai"] += 1
            else:
                manifest["counts"]["fallback"] += 1
            manifest["records"].append(record_status)
            print(f"Wrote {output_path}")
            time.sleep(0.1)
        except Exception as exc:
            record_status["status"] = "failed"
            record_status["problems"].append(str(exc))
            manifest["counts"]["failed"] += 1
            manifest["records"].append(record_status)
            print(f"Failed {parcel}: {exc}")
            if not args.allow_ai_fallback:
                raise
    manifest["finished_at"] = datetime.now().isoformat(timespec="seconds")
    if args.manifest:
        manifest_path = Path(args.manifest)
        if not manifest_path.is_absolute():
            manifest_path = base_dir / manifest_path
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Wrote manifest {manifest_path}")
    print(f"Generated {manifest['counts']['generated']} report(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# © PilotPoint IQ Roof Intelligence All rights reserved
