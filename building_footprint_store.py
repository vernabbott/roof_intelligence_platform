#!/usr/bin/env python3
"""Bounded raw/canonical PostGIS reads and footprint reconciliation storage."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from shapely import normalize, to_wkb, wkt
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool


RAW_TABLE = "building_footprints"
CANONICAL_TABLE = "canonical_building_footprints"
MICROSOFT_SOURCE = "Microsoft US Building Footprints"
MAX_BUILDINGS_PER_REQUEST = 10_000
CANONICAL_REVALIDATION_DAYS = 30
_ENGINE: Engine | None = None


def database_url() -> str:
    load_dotenv(Path(__file__).resolve().parent / ".env")
    configured = os.getenv("DATABASE_URL")
    if configured:
        if configured.startswith("postgres://"):
            return configured.replace("postgres://", "postgresql+psycopg2://", 1)
        if configured.startswith("postgresql://"):
            return configured.replace("postgresql://", "postgresql+psycopg2://", 1)
        return configured
    host = os.getenv("SUPABASE_DB_HOST")
    password = os.getenv("SUPABASE_DB_PASSWORD")
    if not host or not password:
        raise RuntimeError("Supabase building-footprint database configuration is missing")
    port = os.getenv("SUPABASE_DB_PORT", "5432")
    name = os.getenv("SUPABASE_DB_NAME", "postgres")
    user = os.getenv("SUPABASE_DB_USER", "postgres")
    return f"postgresql+psycopg2://{user}:{quote_plus(password)}@{host}:{port}/{name}?sslmode=require"


def engine() -> Engine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(
            database_url(),
            poolclass=NullPool,
            connect_args={
                "sslmode": "require",
                "connect_timeout": 15,
                "options": "-c statement_timeout=60000",
                "application_name": "pilotpoint_request_footprints",
            },
        )
    return _ENGINE


def parse_envelope(value: str) -> tuple[float, float, float, float]:
    try:
        minx, miny, maxx, maxy = (float(part) for part in value.split(","))
    except (TypeError, ValueError) as exc:
        raise ValueError("Building-footprint geometry must be a four-number envelope") from exc
    if minx >= maxx or miny >= maxy:
        raise ValueError("Building-footprint envelope bounds are invalid")
    return minx, miny, maxx, maxy


def _limit(value: int | None) -> int:
    result = min(int(value or MAX_BUILDINGS_PER_REQUEST), MAX_BUILDINGS_PER_REQUEST)
    return max(0, result)


def _record(row) -> dict:
    result = dict(row)
    result.update(
        {
            "OBJECTID": result.get("id"),
            "building_shape_area": result.get("footprint_sqft"),
            "year_built": "",
            "effective_year_built": "",
        }
    )
    return result


def canonical_schema_available(connection=None) -> bool:
    statement = text("SELECT to_regclass(:table_name) IS NOT NULL")
    if connection is not None:
        return bool(connection.execute(statement, {"table_name": CANONICAL_TABLE}).scalar())
    with engine().connect() as current:
        return bool(current.execute(statement, {"table_name": CANONICAL_TABLE}).scalar())


def collect_source_buildings_in_envelope(
    county: str,
    envelope: str,
    source: str = MICROSOFT_SOURCE,
    limit: int | None = None,
) -> list[dict]:
    """Read one explicitly named raw source; never mix overlapping sources."""
    minx, miny, maxx, maxy = parse_envelope(envelope)
    row_limit = _limit(limit)
    if not row_limit:
        return []
    statement = text(
        f"""
        SELECT id, external_id, source, parcel_id, footprint_sqft, perimeter_ft,
               ST_AsText(geometry) AS building_geometry
        FROM {RAW_TABLE}
        WHERE state = 'CO' AND county = :county AND source = :source
          AND geometry && ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326)
          AND ST_Intersects(geometry, ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326))
        ORDER BY footprint_sqft DESC NULLS LAST, id LIMIT :row_limit
        """
    )
    params = {
        "county": county.replace(" County", ""), "source": source,
        "minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy, "row_limit": row_limit,
    }
    with engine().connect() as connection:
        return [_record(row) for row in connection.execute(statement, params).mappings()]


def collect_canonical_buildings_in_envelope(
    county: str, envelope: str, limit: int | None = None
) -> list[dict]:
    minx, miny, maxx, maxy = parse_envelope(envelope)
    row_limit = _limit(limit)
    if not row_limit:
        return []
    statement = text(
        f"""
        SELECT c.id AS canonical_id, c.selected_source_footprint_id AS id,
               c.canonical_key AS external_id, c.selected_source AS source,
               c.parcel_id, b.footprint_sqft, b.perimeter_ft,
               c.resolution_status AS canonical_status, c.difference_pct,
               c.confidence AS canonical_confidence,
               c.validation_details AS canonical_validation,
               c.updated_at AS canonical_updated_at,
               c.updated_at < NOW() - (:revalidation_days * INTERVAL '1 day')
                   AS canonical_revalidation_due,
               EXISTS (
                   SELECT 1
                   FROM building_footprint_source_matches source_match
                   JOIN {RAW_TABLE} source_row
                     ON source_row.id = source_match.source_footprint_id
                   WHERE source_match.canonical_footprint_id = c.id
                     AND COALESCE(source_row.source_updated_at, source_row.imported_at)
                         > c.updated_at
               ) AS canonical_sources_changed,
               ST_AsText(b.geometry) AS building_geometry
        FROM {CANONICAL_TABLE} c
        JOIN {RAW_TABLE} b ON b.id = c.selected_source_footprint_id
        WHERE c.state = 'CO' AND c.county = :county
          AND b.geometry && ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326)
          AND ST_Intersects(b.geometry, ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326))
        ORDER BY b.footprint_sqft DESC, c.id LIMIT :row_limit
        """
    )
    params = {
        "county": county.replace(" County", ""),
        "minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy, "row_limit": row_limit,
        "revalidation_days": CANONICAL_REVALIDATION_DAYS,
    }
    with engine().connect() as connection:
        if not canonical_schema_available(connection):
            return []
        return [_record(row) for row in connection.execute(statement, params).mappings()]


def collect_buildings_in_envelope(
    county: str, envelope: str, limit: int | None = None
) -> list[dict]:
    """Return canonical buildings plus unreconciled Microsoft source records."""
    canonical = collect_canonical_buildings_in_envelope(county, envelope, limit)
    raw = collect_source_buildings_in_envelope(county, envelope, MICROSOFT_SOURCE, limit)
    if not canonical:
        return raw
    matched_ids: set[int] = set()
    with engine().connect() as connection:
        rows = connection.execute(
            text(
                """SELECT source_footprint_id FROM building_footprint_source_matches
                   WHERE canonical_footprint_id = ANY(:ids)"""
            ),
            {"ids": [record["canonical_id"] for record in canonical]},
        )
        matched_ids = {int(row[0]) for row in rows}
    return (canonical + [record for record in raw if int(record["id"]) not in matched_ids])[: _limit(limit)]


def county_source_name(county: str) -> str:
    return f"{county.replace(' County', '')} County GIS Building Footprints"


def canonical_needs_revalidation(record: dict | None) -> bool:
    """Return whether an automatic Microsoft selection needs a live comparison."""
    if not record:
        return False
    if record.get("canonical_status") not in {"validated", "single_source"}:
        return False
    if record.get("source") != MICROSOFT_SOURCE:
        return False
    return bool(
        record.get("canonical_revalidation_due")
        or record.get("canonical_sources_changed")
    )


def _stable_external_id(source: str, geometry_text: str) -> str:
    geometry = normalize(wkt.loads(geometry_text))
    digest = hashlib.sha256(to_wkb(geometry, byte_order=1, include_srid=False)).hexdigest()
    prefix = "".join(ch.lower() if ch.isalnum() else "-" for ch in source).strip("-")[:40]
    return f"{prefix}-{digest}"


def _upsert_secondary_source(connection, county: str, parcel_id: str, record: dict) -> int | None:
    geometry_text = str(record.get("building_geometry") or "").strip()
    if not geometry_text:
        return None
    source = county_source_name(county)
    external_id = str(
        record.get("external_id") or record.get("OBJECTID") or record.get("objectid")
        or _stable_external_id(source, geometry_text)
    )
    source_url = str(record.get("source_url") or "") or None
    result = connection.execute(
        text(
            f"""
            INSERT INTO {RAW_TABLE} (
                external_id, state, county, parcel_id, geometry, centroid,
                footprint_sqft, perimeter_ft, source, source_url,
                source_updated_at, source_metadata
            ) VALUES (
                :external_id, 'CO', :county, :parcel_id,
                ST_Multi(ST_SetSRID(ST_GeomFromText(:geometry), 4326)),
                ST_Centroid(ST_SetSRID(ST_GeomFromText(:geometry), 4326)),
                :area, :perimeter, :source, :source_url,
                :source_updated_at, CAST(:metadata AS jsonb)
            )
            ON CONFLICT (source, external_id) DO UPDATE SET
                parcel_id = COALESCE(EXCLUDED.parcel_id, {RAW_TABLE}.parcel_id),
                geometry = EXCLUDED.geometry, centroid = EXCLUDED.centroid,
                footprint_sqft = EXCLUDED.footprint_sqft,
                source_url = COALESCE(EXCLUDED.source_url, {RAW_TABLE}.source_url),
                source_updated_at = COALESCE(EXCLUDED.source_updated_at, {RAW_TABLE}.source_updated_at),
                source_metadata = EXCLUDED.source_metadata,
                imported_at = NOW()
            RETURNING id
            """
        ),
        {
            "external_id": external_id, "county": county.replace(" County", ""),
            "parcel_id": parcel_id or None, "geometry": geometry_text,
            "area": record.get("footprint_sqft"), "perimeter": record.get("perimeter_ft"),
            "source": source, "source_url": source_url,
            "source_updated_at": record.get("source_updated_at"),
            "metadata": json.dumps({"original_attributes": {k: v for k, v in record.items() if k != "building_geometry"}}, default=str),
        },
    )
    return int(result.scalar_one())


def upsert_county_source_batch(county: str, records: list[dict]) -> int:
    inserted_or_updated = 0
    with engine().begin() as connection:
        if not canonical_schema_available(connection):
            raise RuntimeError("Canonical footprint schema has not been installed")
        for record in records:
            if _upsert_secondary_source(connection, county, str(record.get("parcel_id") or ""), record):
                inserted_or_updated += 1
    return inserted_or_updated


def save_canonical_footprint(
    county: str,
    parcel_id: str,
    primary_record: dict | None,
    secondary_record: dict | None,
    validation: dict,
    *,
    address: str = "",
    selected_source: str = "auto",
    reason: str = "",
    resolved_by: str = "system",
) -> dict:
    """Persist one reconciliation decision and return the canonical record."""
    with engine().begin() as connection:
        if not canonical_schema_available(connection):
            raise RuntimeError("Canonical footprint schema has not been installed")
        primary_id = int(primary_record["id"]) if primary_record and primary_record.get("id") else None
        secondary_id = _upsert_secondary_source(connection, county, parcel_id, secondary_record) if secondary_record else None
        status = str(validation.get("status") or "")
        if selected_source != "auto":
            canonical_status = "manually_resolved"
            chosen = secondary_record if selected_source == "county" else primary_record
            chosen_id = secondary_id if selected_source == "county" else primary_id
        elif status == "discrepancy":
            canonical_status = "pending_review"
            chosen = primary_record or secondary_record
            chosen_id = primary_id or secondary_id
        elif status in {"validated"}:
            canonical_status = "validated"
            chosen, chosen_id = primary_record, primary_id
        else:
            canonical_status = "single_source"
            chosen = primary_record or secondary_record
            chosen_id = primary_id or secondary_id
        if not chosen or not chosen_id:
            raise RuntimeError("A source footprint is required to create a canonical record")
        geometry_text = str(chosen.get("building_geometry") or "")
        area = float(chosen.get("footprint_sqft") or chosen.get("building_footprint_sqft") or 0)
        if not geometry_text or area <= 0:
            raise RuntimeError("Selected canonical footprint is missing geometry or area")
        base_id = primary_id or secondary_id
        canonical_key = f"CO:{county.replace(' County', '')}:source:{base_id}"
        selected_label = str(chosen.get("source") or (county_source_name(county) if chosen is secondary_record else MICROSOFT_SOURCE))
        params = {
            "key": canonical_key, "county": county.replace(" County", ""), "parcel": parcel_id or None,
            "address": " ".join(str(address or "").split()) or None,
            "geometry": geometry_text, "area": area, "perimeter": chosen.get("perimeter_ft"),
            "status": canonical_status, "selected_id": chosen_id, "selected_source": selected_label,
            "source_count": int(bool(primary_id)) + int(bool(secondary_id)),
            "difference": validation.get("difference_pct"),
            "confidence": 1.0 if canonical_status in {"validated", "manually_resolved"} else 0.6,
            "validation": json.dumps(validation, default=str),
            "resolved_by": resolved_by if canonical_status == "manually_resolved" else None,
            "reason": reason if canonical_status == "manually_resolved" else None,
        }
        canonical_id = int(
            connection.execute(
                text(
                    f"""
                    INSERT INTO {CANONICAL_TABLE} (
                        canonical_key, state, county, parcel_id, requested_address, resolution_status,
                        selected_source_footprint_id, selected_source, source_count,
                        difference_pct, confidence, validation_details, validated_at,
                        resolved_at, resolved_by, resolution_reason
                    ) VALUES (
                        :key, 'CO', :county, :parcel, :address, :status, :selected_id, :selected_source,
                        :source_count, :difference, :confidence, CAST(:validation AS jsonb),
                        CASE WHEN :status IN ('validated','single_source') THEN NOW() END,
                        CASE WHEN :status = 'manually_resolved' THEN NOW() END,
                        :resolved_by, :reason
                    )
                    ON CONFLICT (canonical_key) DO UPDATE SET
                        parcel_id = EXCLUDED.parcel_id,
                        requested_address = COALESCE(EXCLUDED.requested_address, {CANONICAL_TABLE}.requested_address),
                        resolution_status = CASE
                            WHEN {CANONICAL_TABLE}.resolution_status = 'manually_resolved'
                            THEN {CANONICAL_TABLE}.resolution_status ELSE EXCLUDED.resolution_status END,
                        selected_source_footprint_id = CASE
                            WHEN {CANONICAL_TABLE}.resolution_status = 'manually_resolved'
                            THEN {CANONICAL_TABLE}.selected_source_footprint_id
                            ELSE EXCLUDED.selected_source_footprint_id END,
                        selected_source = CASE
                            WHEN {CANONICAL_TABLE}.resolution_status = 'manually_resolved'
                            THEN {CANONICAL_TABLE}.selected_source ELSE EXCLUDED.selected_source END,
                        source_count = EXCLUDED.source_count,
                        difference_pct = CASE
                            WHEN {CANONICAL_TABLE}.resolution_status = 'manually_resolved'
                            THEN {CANONICAL_TABLE}.difference_pct ELSE EXCLUDED.difference_pct END,
                        confidence = CASE
                            WHEN {CANONICAL_TABLE}.resolution_status = 'manually_resolved'
                            THEN {CANONICAL_TABLE}.confidence ELSE EXCLUDED.confidence END,
                        validation_details = CASE
                            WHEN {CANONICAL_TABLE}.resolution_status = 'manually_resolved'
                            THEN {CANONICAL_TABLE}.validation_details ELSE EXCLUDED.validation_details END,
                        validated_at = CASE
                            WHEN {CANONICAL_TABLE}.resolution_status = 'manually_resolved'
                            THEN {CANONICAL_TABLE}.validated_at ELSE EXCLUDED.validated_at END,
                        resolved_at = CASE
                            WHEN {CANONICAL_TABLE}.resolution_status = 'manually_resolved'
                            THEN {CANONICAL_TABLE}.resolved_at ELSE EXCLUDED.resolved_at END,
                        resolved_by = CASE
                            WHEN {CANONICAL_TABLE}.resolution_status = 'manually_resolved'
                            THEN {CANONICAL_TABLE}.resolved_by ELSE EXCLUDED.resolved_by END,
                        resolution_reason = CASE
                            WHEN {CANONICAL_TABLE}.resolution_status = 'manually_resolved'
                            THEN {CANONICAL_TABLE}.resolution_reason ELSE EXCLUDED.resolution_reason END,
                        updated_at = NOW()
                    RETURNING id
                    """
                ),
                params,
            ).scalar_one()
        )
        for source_id in (primary_id, secondary_id):
            if source_id:
                connection.execute(
                    text(
                        """INSERT INTO building_footprint_source_matches
                           (canonical_footprint_id, source_footprint_id, overlap_pct, area_difference_pct)
                           VALUES (:canonical, :source, :overlap, :difference)
                           ON CONFLICT (canonical_footprint_id, source_footprint_id) DO UPDATE SET
                             overlap_pct = EXCLUDED.overlap_pct,
                             area_difference_pct = EXCLUDED.area_difference_pct"""
                    ),
                    {"canonical": canonical_id, "source": source_id,
                     "overlap": validation.get("overlap_pct"), "difference": validation.get("difference_pct")},
                )
        if canonical_status == "manually_resolved":
            connection.execute(
                text(
                    """INSERT INTO canonical_footprint_resolutions
                       (canonical_footprint_id, previous_status, selected_source,
                        selected_source_footprint_id, reason, resolved_by, validation_details)
                       VALUES (:canonical, :previous, :source, :source_id, :reason, :user, CAST(:validation AS jsonb))"""
                ),
                {"canonical": canonical_id, "previous": status, "source": selected_label,
                 "source_id": chosen_id, "reason": reason, "user": resolved_by,
                 "validation": json.dumps(validation, default=str)},
            )
    records = collect_canonical_by_id(canonical_id)
    return records


def collect_canonical_by_id(canonical_id: int) -> dict:
    with engine().connect() as connection:
        row = connection.execute(
            text(
                f"""SELECT c.id AS canonical_id, c.selected_source_footprint_id AS id,
                    c.canonical_key AS external_id, c.selected_source AS source, c.parcel_id,
                    b.footprint_sqft, b.perimeter_ft, c.resolution_status AS canonical_status,
                    c.difference_pct, c.confidence AS canonical_confidence,
                    c.validation_details AS canonical_validation,
                    ST_AsText(b.geometry) AS building_geometry
                    FROM {CANONICAL_TABLE} c
                    JOIN {RAW_TABLE} b ON b.id = c.selected_source_footprint_id
                    WHERE c.id = :id"""
            ), {"id": canonical_id}
        ).mappings().one()
    return _record(row)


def mark_canonical_pending_review(canonical_id: int, validation: dict) -> None:
    with engine().begin() as connection:
        connection.execute(
            text(
                f"""UPDATE {CANONICAL_TABLE} SET
                    resolution_status = 'pending_review',
                    difference_pct = :difference,
                    validation_details = CAST(:validation AS jsonb),
                    confidence = 0.5, validated_at = NULL, updated_at = NOW()
                    WHERE id = :id"""
            ),
            {"id": canonical_id, "difference": validation.get("difference_pct"),
             "validation": json.dumps(validation, default=str)},
        )


def list_pending_canonical_footprints(county: str | None = None, limit: int = 100) -> list[dict]:
    conditions = ["c.resolution_status = 'pending_review'"]
    params: dict = {"limit": max(1, min(int(limit), 1000))}
    if county:
        conditions.append("c.county = :county")
        params["county"] = county.replace(" County", "")
    with engine().connect() as connection:
        rows = connection.execute(
            text(
                f"""SELECT c.id AS canonical_id, c.county, c.parcel_id,
                    c.requested_address,
                    c.difference_pct, c.validation_details, c.updated_at,
                    b.id AS selected_source_id, b.source AS selected_source,
                    b.external_id, b.footprint_sqft,
                    COALESCE((
                        SELECT jsonb_agg(jsonb_build_object(
                            'source_footprint_id', source_row.id,
                            'source_type', CASE
                                WHEN source_row.source = :microsoft_source THEN 'microsoft'
                                ELSE 'county'
                            END,
                            'source_name', source_row.source,
                            'footprint_sqft', source_row.footprint_sqft,
                            'source_updated_at', source_row.source_updated_at
                        ) ORDER BY CASE
                            WHEN source_row.source = :microsoft_source THEN 0 ELSE 1
                        END, source_row.id)
                        FROM building_footprint_source_matches source_match
                        JOIN {RAW_TABLE} source_row
                          ON source_row.id = source_match.source_footprint_id
                        WHERE source_match.canonical_footprint_id = c.id
                    ), '[]'::jsonb) AS sources
                    FROM {CANONICAL_TABLE} c
                    JOIN {RAW_TABLE} b ON b.id = c.selected_source_footprint_id
                    WHERE {' AND '.join(conditions)}
                    ORDER BY c.difference_pct DESC NULLS LAST, c.updated_at
                    LIMIT :limit"""
            ), {**params, "microsoft_source": MICROSOFT_SOURCE}
        ).mappings()
        return [dict(row) for row in rows]


def resolve_canonical_footprint(
    canonical_id: int, selected_source: str, reason: str, resolved_by: str
) -> dict:
    selected_source = str(selected_source or "").strip().lower()
    reason = " ".join(str(reason or "").split())
    resolved_by = " ".join(str(resolved_by or "").split())
    if selected_source not in {"microsoft", "county"}:
        raise ValueError("selected_source must be 'microsoft' or 'county'")
    if len(reason) < 10:
        raise ValueError("Canonical resolution reason must be at least 10 characters")
    if not resolved_by:
        raise ValueError("resolved_by is required")
    with engine().begin() as connection:
        canonical = connection.execute(
            text(f"SELECT * FROM {CANONICAL_TABLE} WHERE id=:id FOR UPDATE"), {"id": canonical_id}
        ).mappings().one_or_none()
        if not canonical:
            raise KeyError(canonical_id)
        sources = connection.execute(
            text(
                f"""SELECT b.* FROM building_footprint_source_matches m
                    JOIN {RAW_TABLE} b ON b.id=m.source_footprint_id
                    WHERE m.canonical_footprint_id=:id ORDER BY b.id"""
            ), {"id": canonical_id}
        ).mappings().all()
        chosen = next(
            (
                row for row in sources
                if (selected_source == "microsoft" and row["source"] == MICROSOFT_SOURCE)
                or (selected_source == "county" and row["source"] != MICROSOFT_SOURCE)
            ), None
        )
        if not chosen:
            raise ValueError(f"The canonical record has no {selected_source} source footprint")
        connection.execute(
            text(
                f"""UPDATE {CANONICAL_TABLE} SET resolution_status='manually_resolved',
                    selected_source_footprint_id=:source_id, selected_source=:source,
                    confidence=1.0, resolved_at=NOW(), resolved_by=:user,
                    resolution_reason=:reason, updated_at=NOW() WHERE id=:id"""
            ), {"id": canonical_id, "source_id": chosen["id"], "source": chosen["source"],
                "user": resolved_by, "reason": reason}
        )
        connection.execute(
            text(
                """INSERT INTO canonical_footprint_resolutions
                    (canonical_footprint_id, previous_status, selected_source,
                     selected_source_footprint_id, reason, resolved_by, validation_details)
                    VALUES (:id, :previous, :source, :source_id, :reason, :user, CAST(:validation AS jsonb))"""
            ), {"id": canonical_id, "previous": canonical["resolution_status"],
                "source": chosen["source"], "source_id": chosen["id"], "reason": reason,
                "user": resolved_by, "validation": json.dumps(canonical["validation_details"], default=str)}
        )
    return collect_canonical_by_id(canonical_id)


__all__ = [
    "MICROSOFT_SOURCE", "canonical_needs_revalidation", "canonical_schema_available", "collect_buildings_in_envelope",
    "collect_canonical_buildings_in_envelope", "collect_source_buildings_in_envelope",
    "county_source_name", "mark_canonical_pending_review", "parse_envelope",
    "list_pending_canonical_footprints", "resolve_canonical_footprint",
    "save_canonical_footprint", "upsert_county_source_batch",
]
