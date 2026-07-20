#!/usr/bin/env python3
"""Collect county buildings with parcel, assessor, and imagery information."""

from __future__ import annotations

import json
import os
import re
import time
from io import BytesIO
from math import ceil, floor
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode, urlparse
from urllib.request import Request, urlopen

from PIL import Image, ImageStat
from shapely import wkt
from shapely.errors import ShapelyError
from shapely.geometry import shape
from shapely.ops import transform
from shapely.strtree import STRtree
from pyproj import Transformer

from county_config import county_profile
from footprint_comparison import compare_microsoft_to_county

# TODO: integrate NOAA hail exposure data
# TODO: integrate permit history for recent roof work
# TODO: integrate historical imagery to detect roof condition changes
# TODO: integrate AI roof condition analysis and water damage / insurance indicators

BUILDINGS_URL = ""
PARCELS_URL = ""

PAGE_SIZE = 2000
REQUEST_TIMEOUT = 120
REQUEST_ATTEMPTS = 4
IMAGE_SIZE = "640,640"
IMAGE_FORMAT = "jpgpng"
IMAGE_CRS = 3857
DRCOG_TILE_INDEX_CRS = 6428
AI_CROP_TILE_SERVICE_URL = (
    "https://tiles.arcgis.com/tiles/zdB7qR0BtYrg0Xpl/arcgis/rest/services/"
    "Aerial2018_tilecache/MapServer"
)
AI_CROP_TILE_LEVEL = 19
AI_CROP_BUFFER_FEET = 40.0
AI_CROP_PIXELS = 1536
AI_CROP_FORMAT = "jpg"

BUILDING_FIELDS = [
    "OBJECTID",
    "BUILDING_I",
    "BLDG_TYPE",
    "BLDG_HEIGH",
    "GROUND_ELE",
    "SOURCE",
    "CREATEDATE",
    "Shape__Area",
    "Shape__Length",
]

OPTIONAL_BUILDING_FIELDS = [
    "Building_ID",
    "Bldg_Height",
    "Ground_Elevation",
    "Bldg_Type",
    "Source",
    "CreateDate",
    "objectid",
    "building_id",
    "bldg_height",
    "ground_elevation",
    "bldg_type",
    "source",
    "createdate",
    "SHAPE__Area",
    "SHAPE__Length",
    "Bldg_ID",
    "PARCELNB",
    "PropertyType",
    "OccDesc",
]

PARCEL_FIELDS = [
    "SCHEDNUM",
    "MAPNUM",
    "BLKNUM",
    "PARCELNUM",
    "APPENDAGE",
    "OWNER_NAME",
    "OWNER_ADDRESS_LINE1",
    "OWNER_CITY",
    "OWNER_STATE",
    "OWNER_ZIP",
    "SITUS_ADDRESS_LINE1",
    "SITUS_CITY",
    "SITUS_STATE",
    "TAX_DIST",
    "PROP_CLASS",
    "D_CLASS",
    "D_CLASS_CN",
    "ZONE_ID",
    "ZONE_10",
    "APPRAISED_LAND_VALUE",
    "APPRAISED_IMP_VALUE",
    "LAND_AREA",
    "COM_ORIG_YEAR_BUILT",
    "COM_STRUCTURE_TYPE",
    "Shape__Area",
    "Shape__Length",
]

OPTIONAL_PARCEL_ZIP_FIELDS = [
    "SITUS_ZIP",
    "SITUS_ZIP_CODE",
    "SITE_ZIP",
    "PROPERTY_ZIP",
    "PROP_ZIP",
    "ZIPCODE",
    "ZIP_CODE",
    "Zip",
    "PRPZIP5",
    "loczip",
]

OPTIONAL_PARCEL_FIELDS = [
    "ParcelNo",
    "PARCELNUMBER",
    "PARCELNUM",
    "PARCEL_SPN",
    "PARCEL",
    "PropertyAddress",
    "SITUS_FULL_ADDRESS",
    "LOCADDRESS",
    "LOCZIPCODE",
    "LOCCITY",
    "SITUS",
    "PARCELID",
    "SPN",
    "AIN",
    "OWNNAM",
    "OWNNAM2",
    "OWNNAM3",
    "DBA",
    "MAILCTYNAM",
    "MAILSTENAM",
    "MAILZIP5",
    "PRPADDRESS",
    "PRPCTYNAM",
    "PRPSTENAM",
    "TAXCLS",
    "TAXCLS2",
    "TAXCLS3",
    "STTTYPUSE",
    "STTYRBLT",
    "STTNBRFLR",
    "STTTYPCNS",
    "TOTACR",
    "TOTACTVAL",
    "TOTACTLNDV",
    "TOTACTIMPV",
    "PARCEL_ID",
    "PIN",
    "Folio",
    "Situs_Address",
    "Situs_City_State_Zip",
    "Owner",
    "Owner_Mail_Address",
    "Owner_City_State_Zip",
    "Classification",
    "Neighborhood_Code",
    "Neighborhood",
    "Appr_Value",
    "Imp_Value",
    "Land_Value",
    "Assd_Value",
    "Taxable",
    "PUC_Code",
    "PUC",
    "GIS_AREA",
    "GIS_PERIMETER",
    "Addr_NUM",
    "Pre_Dir",
    "Street",
    "St_Type",
    "Post_Dir",
    "Unit",
    "City",
    "State",
    "PARCELNB",
    "subname",
    "streetno",
    "streetdir",
    "streetname",
    "streetsuf",
    "streetpostdir",
    "streetalp",
    "loccity",
    "concataddr1",
    "concataddr2",
    "ownername1",
    "ownername2",
    "ownernamefull",
    "owneraddress",
    "owneraddressfull",
    "ownercity",
    "ownerstate",
    "ownerzip",
    "ownercsz",
    "legal",
]

_COLLECT_PARCEL_FIELDS: list[str] | None = None
_COLLECT_BUILDING_FIELDS: list[str] | None = None
_LAYER_OID_FIELDS: dict[str, str] = {}

OUTPUT_FIELDS = [
    ("county", "County"),
    ("property_address", "Address"),
    ("property_city", "Building City"),
    ("property_state", "Building State"),
    ("property_zip", "Building ZIP"),
    ("building_footprint", "Building Footprint"),
    ("building_footprint_sqft", "Building Footprint Sq Ft"),
    ("parcel_number", "Parcel Number"),
    ("year_built", "Year Built"),
    ("effective_year_built", "Effective Year Built"),
    ("property_use", "Property Use"),
    ("stories", "Stories"),
    ("land_area_acres", "Land Area"),
    ("construction_type", "Construction Type"),
    ("tax_district", "Tax District"),
    ("land_value", "Land Value"),
    ("primary_aerial_source", "Primary Aerial Source"),
    ("primary_aerial_image_url", "Primary Aerial Image URL"),
    ("primary_aerial_photo_date", "Primary Aerial Photo Date"),
    ("primary_aerial_native_resolution", "Primary Aerial Native Resolution"),
    ("primary_aerial_image_file", "Primary Aerial Image File"),
    ("primary_aerial_qa_status", "Primary Aerial QA Status"),
    ("primary_aerial_qa_reason", "Primary Aerial QA Reason"),
    ("primary_aerial_qa_blank", "Primary Aerial QA Blank"),
    ("primary_aerial_qa_width", "Primary Aerial QA Width"),
    ("primary_aerial_qa_height", "Primary Aerial QA Height"),
    ("primary_aerial_qa_brightness", "Primary Aerial QA Brightness"),
    ("primary_aerial_qa_contrast", "Primary Aerial QA Contrast"),
]

IMAGERY_SOURCES: list[dict] = []
ACTIVE_COUNTY_NAME = ""
ACTIVE_STATE = "CO"


BUILDING_CRS = None
PARCEL_CRS = None
TRANSFORMER_TO_PARCEL = None
TRANSFORMER_TO_BUILDING = None
TRANSFORMER_TO_IMAGE = None
TRANSFORMER_TO_DRCOG_TILE = None
BUILDING_SOURCE_KIND = ""


def metadata_url(url: str) -> str:
    clean_url = url.split("?", 1)[0].rstrip("/")
    if clean_url.endswith("/query"):
        clean_url = clean_url[: -len("/query")]
    return clean_url


def fetch_json(url: str) -> dict | None:
    try:
        separator = "&" if "?" in url else "?"
        request = Request(
            url if "f=json" in url else url + separator + "f=json",
            headers={"User-Agent": "Python Building Collector"},
        )
        with urlopen(request, timeout=30) as resp:
            return json.load(resp)
    except Exception:
        return None


def fetch_arcgis_json(full_url: str) -> dict:
    """Fetch an ArcGIS JSON URL with retries for transient read timeouts."""
    last_exc: Exception | None = None
    for attempt in range(1, REQUEST_ATTEMPTS + 1):
        request = Request(full_url, headers={"User-Agent": "Python Building Collector"})
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return json.load(response)
        except HTTPError as exc:
            last_exc = exc
            if exc.code < 500 or attempt == REQUEST_ATTEMPTS:
                raise RuntimeError(f"HTTP error: {exc.code} {exc.reason}") from exc
        except (TimeoutError, URLError, OSError) as exc:
            last_exc = exc
            if attempt == REQUEST_ATTEMPTS:
                raise RuntimeError(f"URL error after {REQUEST_ATTEMPTS} attempts: {exc}") from exc
        time.sleep(2 * attempt)
    raise RuntimeError(f"URL error: {last_exc}")


def inspect_service_metadata(url: str) -> dict:
    """Return spatialReference metadata for a FeatureServer/Layer URL."""
    meta = fetch_json(metadata_url(url))
    if not meta:
        return {}
    sr = (
        meta.get("spatialReference")
        or (meta.get("extent") or {}).get("spatialReference")
        or meta.get("sourceSpatialReference")
        or {}
    )
    return sr


def init_crs_transformers(
    building_url: str, parcel_url: str, building_crs: int | None = None
) -> None:
    """Inspect services and initialize CRS and Transformers globally."""
    global BUILDING_CRS, PARCEL_CRS, TRANSFORMER_TO_PARCEL, TRANSFORMER_TO_BUILDING, TRANSFORMER_TO_IMAGE, TRANSFORMER_TO_DRCOG_TILE
    bmeta = inspect_service_metadata(building_url) if building_url else {}
    pmeta = inspect_service_metadata(parcel_url)
    # spatialReference may include wkid or latestWkid
    def pick_wkid(meta: dict):
        if not meta:
            return None
        for key in ("latestWkid", "wkid", "wkt"):
            if key in meta:
                if key == "wkt":
                    return None
                return int(meta[key])
        return None

    BUILDING_CRS = building_crs or pick_wkid(bmeta)
    PARCEL_CRS = pick_wkid(pmeta)

    if BUILDING_CRS is None or PARCEL_CRS is None:
        raise RuntimeError(
            "Unable to determine building/parcel coordinate systems; "
            "aborting before aerial imagery can be requested at the wrong location."
        )

    print(f"Buildings CRS: {BUILDING_CRS}")
    print(f"Parcels CRS: {PARCEL_CRS}")

    try:
        if BUILDING_CRS and PARCEL_CRS and BUILDING_CRS != PARCEL_CRS:
            TRANSFORMER_TO_PARCEL = Transformer.from_crs(BUILDING_CRS, PARCEL_CRS, always_xy=True)
            TRANSFORMER_TO_BUILDING = Transformer.from_crs(PARCEL_CRS, BUILDING_CRS, always_xy=True)
        else:
            TRANSFORMER_TO_PARCEL = None
            TRANSFORMER_TO_BUILDING = None
        if BUILDING_CRS and BUILDING_CRS != IMAGE_CRS:
            TRANSFORMER_TO_IMAGE = Transformer.from_crs(BUILDING_CRS, IMAGE_CRS, always_xy=True)
        else:
            TRANSFORMER_TO_IMAGE = None
        if BUILDING_CRS and BUILDING_CRS != DRCOG_TILE_INDEX_CRS:
            TRANSFORMER_TO_DRCOG_TILE = Transformer.from_crs(BUILDING_CRS, DRCOG_TILE_INDEX_CRS, always_xy=True)
        else:
            TRANSFORMER_TO_DRCOG_TILE = None
    except Exception:
        TRANSFORMER_TO_PARCEL = None
        TRANSFORMER_TO_BUILDING = None
        TRANSFORMER_TO_IMAGE = None
        TRANSFORMER_TO_DRCOG_TILE = None


def esri_geometry_to_geojson(geometry: dict | None) -> dict | None:
    if not geometry:
        return None
    if "rings" in geometry:
        rings = geometry.get("rings")
        if not rings:
            return None
        return {"type": "Polygon", "coordinates": rings}
    if "paths" in geometry:
        paths = geometry.get("paths")
        if not paths:
            return None
        return {"type": "LineString", "coordinates": paths[0]}
    return None


def geometry_to_wkt(geometry: dict | None) -> str:
    geojson = esri_geometry_to_geojson(geometry)
    if not geojson:
        return ""
    try:
        poly = shape(geojson)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            return ""
        return wkt.dumps(poly)
    except (ShapelyError, ValueError):
        return ""


def build_polygon_from_esri(geometry: dict | None, transform_to_parcel: bool = False) -> object | None:
    geojson = esri_geometry_to_geojson(geometry)
    if not geojson:
        return None
    try:
        polygon = shape(geojson)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.is_empty:
            return None
        if transform_to_parcel and TRANSFORMER_TO_PARCEL is not None:
            polygon = transform(TRANSFORMER_TO_PARCEL.transform, polygon)
            if not polygon.is_valid:
                polygon = polygon.buffer(0)
            if polygon.is_empty:
                return None
        return polygon
    except (ShapelyError, ValueError):
        return None


def fetch_page(url: str, where: str, offset: int, out_fields: Iterable[str], return_geometry: bool = False) -> dict:
    oid_field = _LAYER_OID_FIELDS.get(url)
    if not oid_field:
        metadata = fetch_json(layer_metadata_url(url)) or {}
        oid_field = str(metadata.get("objectIdField") or metadata.get("objectIdFieldName") or "OBJECTID")
        _LAYER_OID_FIELDS[url] = oid_field
    params = {
        "where": where,
        "outFields": ",".join(out_fields),
        "returnGeometry": "true" if return_geometry else "false",
        "f": "json",
        "resultOffset": offset,
        "resultRecordCount": PAGE_SIZE,
        "orderByFields": f"{oid_field} ASC",
    }
    full_url = url + "?" + urlencode(params)
    return fetch_arcgis_json(full_url)


def layer_metadata_url(url: str) -> str:
    clean_url = url.split("?", 1)[0].rstrip("/")
    if clean_url.endswith("/query"):
        clean_url = clean_url[: -len("/query")]
    return clean_url


def available_layer_fields(url: str) -> list[dict]:
    metadata = fetch_json(layer_metadata_url(url)) or {}
    return metadata.get("fields", [])


def collect_available_fields(url: str, preferred_fields: Iterable[str], fallback: str = "*") -> list[str]:
    field_names = {field.get("name") for field in available_layer_fields(url)}
    if not field_names:
        return list(preferred_fields) or [fallback]
    fields = [field for field in preferred_fields if field in field_names]
    if "OBJECTID" in field_names and "OBJECTID" not in fields:
        fields.insert(0, "OBJECTID")
    return fields or [fallback]


def collect_building_fields(url: str | None = None) -> list[str]:
    global _COLLECT_BUILDING_FIELDS
    if _COLLECT_BUILDING_FIELDS is not None:
        return _COLLECT_BUILDING_FIELDS
    url = url or BUILDINGS_URL
    _COLLECT_BUILDING_FIELDS = collect_available_fields(url, BUILDING_FIELDS + OPTIONAL_BUILDING_FIELDS)
    return _COLLECT_BUILDING_FIELDS


def collect_parcel_fields(url: str | None = None) -> list[str]:
    global _COLLECT_PARCEL_FIELDS
    if _COLLECT_PARCEL_FIELDS is not None:
        return _COLLECT_PARCEL_FIELDS
    url = url or PARCELS_URL
    _COLLECT_PARCEL_FIELDS = collect_available_fields(
        url,
        PARCEL_FIELDS + OPTIONAL_PARCEL_FIELDS + OPTIONAL_PARCEL_ZIP_FIELDS,
    )
    return _COLLECT_PARCEL_FIELDS


def normalize_zip(value: object) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[:5]


def parcel_zip(record: dict) -> str:
    for field in (
        "SITUS_ZIP",
        "SITUS_ZIP_CODE",
        "SITE_ZIP",
        "PROPERTY_ZIP",
        "PROP_ZIP",
        "ZIPCODE",
        "ZIP_CODE",
        "Zip",
        "PRPZIP5",
        "loczip",
        "LOCZIPCODE",
    ):
        zip_code = normalize_zip(record.get(field))
        if zip_code:
            return zip_code
    zip_code = normalize_zip(record.get("Situs_City_State_Zip"))
    if zip_code:
        return zip_code
    return ""


def parcel_zip_where(zip_codes: set[str]) -> str:
    if not zip_codes:
        return "1=1"
    fields = set(collect_parcel_fields(PARCELS_URL))
    clauses: list[str] = []
    if "Zip" in fields:
        clauses.extend(f"Zip LIKE '{zip_code}%'" for zip_code in sorted(zip_codes))
    else:
        for field in (
            "SITUS_ZIP",
            "SITUS_ZIP_CODE",
            "SITE_ZIP",
            "PROPERTY_ZIP",
            "PROP_ZIP",
            "ZIPCODE",
            "ZIP_CODE",
            "PRPZIP5",
            "loczip",
        ):
            if field in fields:
                clauses.extend(f"{field} LIKE '{zip_code}%'" for zip_code in sorted(zip_codes))
                break
    return "(" + " OR ".join(clauses) + ")" if clauses else "1=1"


def get_parcel_bounds_in_building_crs(parcels: list[dict]) -> str | None:
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for parcel in parcels:
        parcel_poly = get_parcel_polygon(parcel)
        if parcel_poly is None:
            continue
        try:
            if TRANSFORMER_TO_BUILDING is not None:
                parcel_geo = transform(TRANSFORMER_TO_BUILDING.transform, parcel_poly)
            else:
                parcel_geo = parcel_poly
        except Exception:
            continue
        if parcel_geo.is_empty:
            continue
        x0, y0, x1, y1 = parcel_geo.bounds
        minx = min(minx, x0)
        miny = min(miny, y0)
        maxx = max(maxx, x1)
        maxy = max(maxy, y1)
    if minx == float("inf") or miny == float("inf"):
        return None
    return f"{minx},{miny},{maxx},{maxy}"


def collect_buildings(fetch_limit: int | None = None, geometry: str | None = None) -> list[dict]:
    """Fetch buildings, optionally constrained by a geometry filter."""
    if not ACTIVE_COUNTY_NAME or not BUILDING_SOURCE_KIND:
        raise RuntimeError("Collector must be configured with an explicit county profile")
    if BUILDING_SOURCE_KIND == "postgis":
        if not geometry:
            raise ValueError("PostGIS building discovery requires a selected geometry envelope")
        from building_footprint_store import collect_buildings_in_envelope

        return collect_buildings_in_envelope(ACTIVE_COUNTY_NAME, geometry, fetch_limit)
    raise RuntimeError(f"Unsupported building source: {BUILDING_SOURCE_KIND}")


def geometry_area_sqft_wgs84(geometry_text: str) -> float:
    polygon = build_polygon_from_wkt(geometry_text)
    if polygon is None:
        return 0.0
    projected = transform(Transformer.from_crs(4326, 26913, always_xy=True).transform, polygon)
    return float(projected.area) * 10.76391041671


def collect_secondary_buildings(
    fetch_limit: int | None = None, geometry: str | None = None
) -> list[dict]:
    """Fetch a bounded county footprint layer when PostGIS is the primary source."""
    if BUILDING_SOURCE_KIND != "postgis" or not BUILDINGS_URL:
        return []
    if not geometry:
        raise ValueError("Secondary building discovery requires a selected geometry envelope")
    row_limit = min(int(fetch_limit or 10_000), 10_000)
    offset = 0
    records: list[dict] = []
    fields = collect_available_fields(
        BUILDINGS_URL, BUILDING_FIELDS + OPTIONAL_BUILDING_FIELDS
    )
    oid_field = _LAYER_OID_FIELDS.get(BUILDINGS_URL)
    if not oid_field:
        metadata = fetch_json(layer_metadata_url(BUILDINGS_URL)) or {}
        oid_field = str(
            metadata.get("objectIdField")
            or metadata.get("objectIdFieldName")
            or "OBJECTID"
        )
        _LAYER_OID_FIELDS[BUILDINGS_URL] = oid_field
    while len(records) < row_limit:
        params = {
            "where": "1=1",
            "outFields": ",".join(fields),
            "returnGeometry": "true",
            "geometry": geometry,
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": "4326",
            "outSR": "4326",
            "resultOffset": offset,
            "resultRecordCount": min(PAGE_SIZE, row_limit - len(records)),
            "orderByFields": f"{oid_field} ASC",
            "f": "json",
        }
        page = fetch_arcgis_json(BUILDINGS_URL + "?" + urlencode(params))
        features = page.get("features") or []
        for feature in features:
            attrs = dict(feature.get("attributes") or {})
            geometry_text = geometry_to_wkt(feature.get("geometry"))
            attrs.update(
                {
                    "building_esri_geometry": feature.get("geometry"),
                    "building_geometry": geometry_text,
                    "footprint_sqft": geometry_area_sqft_wgs84(geometry_text),
                    "footprint_source": "county_gis",
                    "year_built": "",
                    "effective_year_built": "",
                }
            )
            records.append(attrs)
        if len(features) < min(PAGE_SIZE, row_limit - offset):
            break
        offset += len(features)
    return records[:row_limit]


def validate_building_footprint_sources(
    primary_record: dict,
    secondary_buildings: list[dict],
    tolerance: float = 0.05,
) -> dict:
    """Compare the selected Supabase footprint with the overlapping county footprint."""
    primary_polygon = build_polygon_from_wkt(primary_record.get("building_geometry") or "")
    primary_area = numeric_value(
        primary_record.get("footprint_sqft")
        or primary_record.get("building_footprint_sqft")
        or primary_record.get("projected_building_footprint_area")
    )
    if primary_polygon is None or not primary_area:
        return {"status": "primary_unavailable", "primary_sqft": primary_area or 0.0}

    projected_primary = transform(
        Transformer.from_crs(4326, 26913, always_xy=True).transform, primary_polygon
    )
    best: tuple[float, dict] | None = None
    for record in secondary_buildings:
        polygon = build_polygon_from_wkt(record.get("building_geometry") or "")
        if polygon is None:
            continue
        projected = transform(
            Transformer.from_crs(4326, 26913, always_xy=True).transform, polygon
        )
        intersection = projected_primary.intersection(projected).area
        if intersection <= 0:
            continue
        overlap = intersection / max(projected_primary.union(projected).area, 1.0)
        if best is None or overlap > best[0]:
            best = (overlap, record)

    if best is None:
        return {
            "status": "primary_only",
            "primary_sqft": round(float(primary_area), 1),
            "secondary_sqft": 0.0,
        }
    secondary_area = numeric_value(best[1].get("footprint_sqft")) or 0.0
    comparison = compare_microsoft_to_county(primary_area, secondary_area, tolerance)
    return {
        **comparison,
        "primary_sqft": round(float(primary_area), 1),
        "secondary_sqft": round(secondary_area, 1),
        "overlap_pct": round(best[0] * 100, 2),
    }


def build_polygon_from_wkt(wkt_text: str) -> object | None:
    if not wkt_text:
        return None
    try:
        polygon = wkt.loads(wkt_text)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.is_empty:
            return None
        return polygon
    except (ShapelyError, ValueError):
        return None


def get_building_polygon(record: dict) -> object | None:
    polygon = build_polygon_from_esri(record.get("building_esri_geometry"), transform_to_parcel=True)
    if polygon is not None:
        return polygon
    polygon = build_polygon_from_wkt(record.get("building_geometry") or "")
    if polygon is None:
        return None
    if TRANSFORMER_TO_PARCEL is not None:
        try:
            polygon = transform(TRANSFORMER_TO_PARCEL.transform, polygon)
        except Exception:
            return None
    return polygon if not polygon.is_empty else None


def get_parcel_polygon(record: dict) -> object | None:
    return build_polygon_from_wkt(record.get("parcel_geometry", ""))


def match_building_to_parcel(
    building_poly: object,
    parcel_index: STRtree,
    parcel_polygons: list[object],
    valid_parcels: list[dict],
) -> dict | None:
    if building_poly is None:
        return None

    candidate_indices = parcel_index.query(building_poly)
    if candidate_indices is None or len(candidate_indices) == 0:
        return None

    best_match = None
    for index in candidate_indices:
        if not isinstance(index, int) and not hasattr(index, 'item'):
            continue
        try:
            candidate_poly = parcel_polygons[int(index)]
        except (IndexError, TypeError, ValueError):
            continue
        if candidate_poly is None:
            continue

        if building_poly.centroid.within(candidate_poly):
            try:
                return valid_parcels[int(index)]
            except Exception:
                return None
        if building_poly.intersects(candidate_poly):
            best_match = candidate_poly
            best_index = int(index)

    if best_match is not None:
        try:
            return valid_parcels[int(best_index)]
        except Exception:
            return None
    return None


def calculate_roof_area_est(record: dict) -> int:
    value = record.get("projected_roof_area")
    if value in (None, ""):
        value = record.get("building_shape_area")
    if value in (None, ""):
        value = record.get("Shape__Area")
    try:
        area = float(value)
    except (TypeError, ValueError):
        return 0
    return round(area)


def calculate_building_footprint_sqft(record: dict) -> int:
    value = record.get("projected_building_footprint_area")
    if value in (None, ""):
        value = record.get("projected_roof_area")
    try:
        area = float(value)
    except (TypeError, ValueError):
        return 0
    return round(area)


def calculate_roof_squares(record: dict) -> float:
    try:
        roof_area = float(record.get("roof_area_est", 0) or 0)
    except (TypeError, ValueError):
        roof_area = 0
    squares = roof_area / 100.0
    return round(squares, 1)


def normalize_key(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isalnum()).upper()


def parcel_join_key(record: dict) -> str:
    if not ACTIVE_COUNTY_NAME:
        raise RuntimeError("Collector must be configured with an explicit county profile")
    county_key = ACTIVE_COUNTY_NAME.strip().lower().replace(" county", "").replace(" ", "_")
    configured_fields = county_profile(county_key).parcel_id_fields
    for field in configured_fields + (
        "PARID", "ParcelNo", "PARCELNUMBER", "PARCELNUM", "PARCEL_SPN", "PARCEL_ID",
        "PARCELID", "PARCELNB", "PARCEL", "PIN", "SPN", "AIN", "Folio", "SCHEDNUM",
        "parcel_number",
    ):
        value = normalize_key(record.get(field))
        if value:
            return value
    pieces = [record.get("MAPNUM"), record.get("BLKNUM"), record.get("PARCELNUM"), record.get("APPENDAGE")]
    joined = normalize_key("".join(str(piece or "") for piece in pieces))
    return joined


def address_from_record(record: dict) -> str:
    direct = str(
        record.get("SITUS_ADDRESS_LINE1")
        or record.get("Situs_Address")
        or record.get("PRPADDRESS")
        or record.get("concataddr1")
        or record.get("PropertyAddress")
        or record.get("SITUS_FULL_ADDRESS")
        or record.get("LOCADDRESS")
        or record.get("SITUS")
        or ""
    ).strip()
    if direct:
        return direct
    parts = [
        record.get("SITE_NBR"),
        record.get("SITE_DIR"),
        record.get("SITE_NAME"),
        record.get("SITE_MODE"),
        record.get("SITE_MORE"),
    ]
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def property_use_text(record: dict) -> str:
    fields = (
        "PROPERTY_CLASS_DESC",
        "D_CLASS_CN",
        "COM_STRUCTURE_TYPE",
        "PUC",
        "PUC_Code",
        "BLDG_TYPE",
        "Bldg_Type",
        "bldg_type",
        "STTTYPUSE",
        "PROP_CLASS",
        "PROP_CLASS_LAND",
        "PROP_CLASS_IMPS",
        "TAXCLS",
        "TAXCLS2",
        "TAXCLS3",
        "PropertyType",
        "OccDesc",
    )
    return " ".join(str(record.get(field) or "") for field in fields).strip()


def first_nonempty(record: dict, fields: tuple[str, ...]) -> object:
    for field in fields:
        value = record.get(field)
        if value not in (None, "", 0, "0"):
            return value
    return ""


def numeric_value(value: object) -> float | None:
    try:
        return float(str(value or "").replace(",", ""))
    except ValueError:
        return None


def land_area_acres(record: dict) -> str:
    value = first_nonempty(record, ("TOTACR",))
    acres = numeric_value(value)
    if acres is not None and acres > 0:
        return f"{acres:.2f}"
    value = first_nonempty(record, ("LAND_AREA", "GIS_AREA", "parcel_shape_area", "Shape__Area"))
    area_sqft = numeric_value(value)
    if area_sqft is None or area_sqft <= 0:
        return ""
    return f"{area_sqft / 43560:.2f}"


def city_state_zip_part(record: dict, part: str) -> str:
    text = str(record.get("Situs_City_State_Zip") or "").strip()
    if not text:
        return ""
    pieces = text.replace(",", " ").split()
    if not pieces:
        return ""
    if part == "state":
        for piece in pieces:
            if len(piece) == 2 and piece.isalpha():
                return piece.upper()
        return ""
    if part == "city":
        state_index = None
        for index, piece in enumerate(pieces):
            if len(piece) == 2 and piece.isalpha():
                state_index = index
                break
        city_pieces = pieces[:state_index] if state_index is not None else pieces[:-1]
        return " ".join(city_pieces).strip()
    return ""


RESIDENTIAL_TERMS = (
    "residential",
    "single family",
    "duplex",
    "triplex",
    "quadplex",
    "apartment",
    "condo",
    "condominium",
    "townhome",
    "rowhouse",
    "mobile home",
)

TARGET_TERMS = (
    "warehouse",
    "industrial",
    "retail",
    "office",
    "commercial",
    "school",
    "church",
    "municipal",
    "government",
    "medical",
    "manufacturing",
    "distribution",
)


def is_target_property(record: dict) -> bool:
    text = property_use_text(record).lower()
    if str(record.get("TAXCLS") or "").startswith("2"):
        return True
    if any(term in text for term in RESIDENTIAL_TERMS):
        return False
    return any(term in text for term in TARGET_TERMS)


def likely_low_slope_roof(record: dict) -> bool:
    return is_target_property(record)


def classify_owner_type(owner_name: object) -> str:
    owner = str(owner_name or "").upper()
    if "SCHOOL DISTRICT" in owner:
        return "School"
    if any(term in owner for term in ("CITY OF", "COUNTY OF", "STATE OF", "CITY & COUNTY")):
        return "Government"
    if any(term in owner for term in ("CHURCH", "MINISTRY", "TEMPLE")):
        return "Religious"
    if any(term in owner for term in ("LLC", "INC", "CORP", " LP", "LTD")):
        return "Commercial Entity"
    return "Unknown"


def add_output_fields(record: dict) -> None:
    record["county"] = record.get("county") or ACTIVE_COUNTY_NAME
    record["property_address"] = address_from_record(record)
    record["property_city"] = record.get("SITUS_CITY") or record.get("PRPCTYNAM") or record.get("City") or record.get("loccity") or city_state_zip_part(record, "city")
    record["property_state"] = record.get("SITUS_STATE") or record.get("PRPSTENAM") or record.get("State") or city_state_zip_part(record, "state") or ACTIVE_STATE
    record["property_zip"] = parcel_zip(record)
    record["owner_name"] = record.get("OWNER") or record.get("OWNER_NAME") or record.get("OWNNAM") or record.get("Owner") or record.get("ownernamefull") or ""
    record["owner_type"] = classify_owner_type(record["owner_name"])
    record["property_use"] = property_use_text(record)
    record["property_use_code"] = record.get("PROP_CLASS_IMPS") or record.get("PROP_CLASS") or record.get("PUC_Code") or record.get("TAXCLS") or ""
    record["property_class"] = record.get("PROPERTY_CLASS_DESC") or record.get("D_CLASS_CN") or record.get("PUC") or record.get("STTTYPUSE") or ""
    record["year_built"] = first_nonempty(record, ("ORIG_YOC", "COM_ORIG_YEAR_BUILT", "RES_ORIG_YEAR_BUILT", "STTYRBLT"))
    record["effective_year_built"] = first_nonempty(
        record,
        (
            "EFFECTIVE_YEAR_BUILT",
            "EFF_YEAR_BUILT",
            "EFF_YR_BUILT",
            "EFF_YOC",
            "COM_EFFECTIVE_YEAR_BUILT",
            "COM_EFF_YEAR_BUILT",
            "REMODEL",
        ),
    )
    record["parcel_number"] = parcel_join_key(record)
    record["building_footprint"] = record.get("building_geometry") or ""
    record["building_footprint_sqft"] = calculate_building_footprint_sqft(record)
    record["stories"] = first_nonempty(record, ("NO_FLOORS", "STORIES", "NUM_STORIES", "NO_STORIES", "STTNBRFLR"))
    record["land_area_acres"] = land_area_acres(record)
    record["construction_type"] = first_nonempty(record, ("COM_STRUCTURE_TYPE", "BLDG_TYPE", "Bldg_Type", "bldg_type", "STTTYPCNS"))
    record["tax_district"] = first_nonempty(record, ("TAX_DIST",))
    record["land_value"] = first_nonempty(record, ("APPRAISED_LAND_VALUE", "ASMT_APPR_LAND", "APPR_LAND_LOC", "Land_Value", "TOTACTLNDV"))
    record["likely_low_slope"] = "TRUE" if likely_low_slope_roof(record) else "FALSE"


def slug(value: object, fallback: str = "record") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:80] or fallback


def building_polygon_in_image_crs(record: dict) -> object | None:
    polygon = build_polygon_from_esri(record.get("building_esri_geometry"), transform_to_parcel=False)
    if polygon is None:
        polygon = build_polygon_from_wkt(record.get("building_geometry") or record.get("building_footprint") or "")
    if polygon is None:
        return None
    if TRANSFORMER_TO_IMAGE is not None:
        polygon = transform(TRANSFORMER_TO_IMAGE.transform, polygon)
    if polygon.is_empty:
        return None
    return polygon


def source_image_crs(source: dict) -> int:
    return int(source.get("image_crs") or IMAGE_CRS)


def building_polygon_for_imagery_source(record: dict, source: dict) -> object | None:
    polygon = build_polygon_from_esri(record.get("building_esri_geometry"), transform_to_parcel=False)
    if polygon is None:
        polygon = build_polygon_from_wkt(record.get("building_geometry") or record.get("building_footprint") or "")
    if polygon is None:
        return None
    target_crs = source_image_crs(source)
    if BUILDING_CRS and BUILDING_CRS != target_crs:
        transformer = Transformer.from_crs(BUILDING_CRS, target_crs, always_xy=True)
        polygon = transform(transformer.transform, polygon)
    if polygon.is_empty:
        return None
    return polygon


def building_polygon_in_drcog_tile_crs(record: dict, source: dict | None = None) -> object | None:
    polygon = build_polygon_from_esri(record.get("building_esri_geometry"), transform_to_parcel=False)
    if polygon is None:
        polygon = build_polygon_from_wkt(record.get("building_geometry") or record.get("building_footprint") or "")
    if polygon is None:
        return None
    target_crs = int((source or {}).get("index_crs") or DRCOG_TILE_INDEX_CRS)
    if BUILDING_CRS and BUILDING_CRS != target_crs:
        transformer = Transformer.from_crs(BUILDING_CRS, target_crs, always_xy=True)
        polygon = transform(transformer.transform, polygon)
    if polygon.is_empty:
        return None
    return polygon


def padded_bounds(bounds: tuple[float, float, float, float], padding_ratio: float = 0.35) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = bounds
    width = max(maxx - minx, 20.0)
    height = max(maxy - miny, 20.0)
    pad = max(width, height) * padding_ratio
    return minx - pad, miny - pad, maxx + pad, maxy + pad


def enforce_minimum_export_resolution(
    bounds: tuple[float, float, float, float], source: dict
) -> tuple[float, float, float, float]:
    """Keep cached imagery requests at or above the source's finest valid scale."""
    try:
        resolution = float(source.get("minimum_export_resolution") or 0)
        pixels = max(int(part) for part in IMAGE_SIZE.split(","))
    except (TypeError, ValueError):
        return bounds
    minimum_side = resolution * pixels
    if minimum_side <= 0:
        return bounds
    minx, miny, maxx, maxy = bounds
    side = max(maxx - minx, maxy - miny, minimum_side)
    center_x = (minx + maxx) / 2
    center_y = (miny + maxy) / 2
    half = side / 2
    return center_x - half, center_y - half, center_x + half, center_y + half


def square_buffered_bounds(
    bounds: tuple[float, float, float, float],
    buffer_feet: float,
    image_units: str = "meters",
) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = bounds
    buffer_distance = max(float(buffer_feet or 0), 0.0)
    if image_units != "feet":
        buffer_distance *= 0.3048
    center_x = (minx + maxx) / 2
    center_y = (miny + maxy) / 2
    side = max(maxx - minx, maxy - miny, 20.0) + (2 * buffer_distance)
    half = side / 2
    return center_x - half, center_y - half, center_x + half, center_y + half


def project_text(value: object) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        return text[:-2]
    return text


def drapp_original_tile_metadata(source: dict, polygon: object) -> dict[str, str]:
    centroid = polygon.centroid
    params = {
        "f": "json",
        "geometry": json.dumps(
            {
                "x": centroid.x,
                "y": centroid.y,
                "spatialReference": {"wkid": DRCOG_TILE_INDEX_CRS},
            }
        ),
        "geometryType": "esriGeometryPoint",
        "inSR": DRCOG_TILE_INDEX_CRS,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "false",
        "resultRecordCount": 1,
    }
    query_url = str(source["index_url"]).rstrip("/") + "/query?" + urlencode(params)
    data = fetch_arcgis_json(query_url)
    features = data.get("features") or []
    if not features:
        return {"url": "", "photo_date": ""}

    attrs = features[0].get("attributes") or {}
    metadata = {"url": "", "photo_date": str(attrs.get(source.get("date_field", "photo_date")) or "")}
    url_field = source.get("url_field")
    if url_field and attrs.get(url_field):
        metadata["url"] = str(attrs[url_field])
        return metadata

    tile = attrs.get("tile")
    project = project_text(attrs.get("project") or source.get("project"))
    if not tile or not project:
        return metadata

    archive_base_url = str(source.get("archive_base_url") or "https://drapparchive.s3.amazonaws.com").rstrip("/")
    metadata["url"] = f"{archive_base_url}/{project}/{tile}.tif"
    return metadata


def drapp_original_tile_url(source: dict, polygon: object) -> str:
    return drapp_original_tile_metadata(source, polygon).get("url", "")


def aerial_image_url(source: dict, bounds: tuple[float, float, float, float], polygon: object) -> str:
    service_url = str(source["url"]).rstrip("/")
    bbox = ",".join(f"{coord:.3f}" for coord in bounds)
    image_crs = source_image_crs(source)
    if source["kind"] == "ImageServer":
        endpoint = service_url + "/exportImage"
        params = {
            "bbox": bbox,
            "bboxSR": image_crs,
            "imageSR": image_crs,
            "size": IMAGE_SIZE,
            "format": IMAGE_FORMAT,
            "f": "image",
        }
    else:
        endpoint = service_url + "/export"
        params = {
            "bbox": bbox,
            "bboxSR": image_crs,
            "imageSR": image_crs,
            "size": IMAGE_SIZE,
            "format": IMAGE_FORMAT,
            "transparent": "false",
            "f": "image",
        }
        if source.get("layers"):
            params["layers"] = str(source["layers"])
    return endpoint + "?" + urlencode(params)


def raster_source_metadata(source: dict, polygon: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "photo_date": "",
        "native_resolution": source.get("native_resolution", ""),
    }
    metadata_layer = source.get("metadata_layer")
    if metadata_layer is None:
        return metadata

    centroid = polygon.centroid
    image_crs = source_image_crs(source)
    service_url = str(source["url"]).rstrip("/")
    params = {
        "where": "1=1",
        "geometry": json.dumps(
            {
                "x": centroid.x,
                "y": centroid.y,
                "spatialReference": {"wkid": image_crs},
            }
        ),
        "geometryType": "esriGeometryPoint",
        "inSR": str(image_crs),
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": ",".join(
            [
                str(source.get("metadata_date_field") or "SRC_DATE"),
                "SRC_DATE2",
                "SRC_RES",
                "SRC_ACC",
                "SRC_DESC",
                "NICE_NAME",
                "NICE_DESC",
                "ReleaseName",
            ]
        ),
        "returnGeometry": "false",
        "resultRecordCount": 1,
        "f": "json",
    }
    query_url = f"{service_url}/{metadata_layer}/query?" + urlencode(params)
    try:
        data = fetch_arcgis_json(query_url)
    except Exception:
        return metadata

    features = data.get("features") or []
    if not features:
        return metadata

    attrs = features[0].get("attributes") or {}
    raw_date = attrs.get(source.get("metadata_date_field") or "SRC_DATE")
    date_text = normalize_esri_date(raw_date)
    if date_text:
        metadata["photo_date"] = date_text
    raw_resolution = attrs.get(source.get("metadata_resolution_field") or "SRC_RES")
    try:
        resolution = float(raw_resolution)
    except (TypeError, ValueError):
        resolution = 0.0
    if resolution > 0:
        metadata["native_resolution"] = resolution
    return metadata


def normalize_esri_date(value: object) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 8:
        return digits
    return ""


def export_raster_crop_url(
    source: dict,
    bounds: tuple[float, float, float, float],
    max_pixels: int,
    image_format: str,
    response_format: str = "image",
) -> str:
    service_url = str(source["url"]).rstrip("/")
    bbox = ",".join(f"{coord:.3f}" for coord in bounds)
    extension = "jpg" if str(image_format).lower() == "jpg" else str(image_format).lower()
    image_crs = source_image_crs(source)
    params = {
        "bbox": bbox,
        "bboxSR": image_crs,
        "imageSR": image_crs,
        "size": f"{int(max_pixels or AI_CROP_PIXELS)},{int(max_pixels or AI_CROP_PIXELS)}",
        "format": extension,
        "f": response_format,
    }
    if source.get("layers"):
        params["layers"] = str(source["layers"])
    endpoint = "/exportImage" if source.get("kind") == "ImageServer" else "/export"
    if source.get("kind") != "ImageServer":
        params["transparent"] = "false"
    return service_url + endpoint + "?" + urlencode(params)


def native_capped_crop_pixels(
    record: dict,
    source: dict,
    bounds: tuple[float, float, float, float],
    requested_pixels: int,
) -> int:
    """Cap an export at configured limits and the source's real pixel size."""
    pixels = max(1, int(requested_pixels or AI_CROP_PIXELS))
    if source.get("max_export_pixels"):
        pixels = min(pixels, int(source["max_export_pixels"]))

    raw_resolution = (
        record.get(f"{source['key']}_aerial_native_resolution")
        or source.get("native_resolution")
    )
    try:
        native_resolution = float(raw_resolution)
    except (TypeError, ValueError):
        native_resolution = 0.0
    if native_resolution <= 0:
        return pixels

    side = max(bounds[2] - bounds[0], bounds[3] - bounds[1])
    native_pixels = max(1, int(ceil(side / native_resolution)))
    minimum_pixels = max(1, int(source.get("min_export_pixels") or 1))
    return min(pixels, max(native_pixels, minimum_pixels))


def add_aerial_image_fields(record: dict) -> None:
    for source in IMAGERY_SOURCES:
        if source["kind"] == "DRAPPOriginalTile":
            polygon = building_polygon_in_drcog_tile_crs(record, source)
            metadata = drapp_original_tile_metadata(source, polygon) if polygon else {"url": "", "photo_date": ""}
            record[f"{source['key']}_aerial_image_url"] = metadata.get("url", "")
            record[f"{source['key']}_aerial_photo_date"] = metadata.get("photo_date") or source.get("photo_date", "")
            record[f"{source['key']}_aerial_native_resolution"] = source.get("native_resolution", "")
            record.setdefault(f"{source['key']}_aerial_image_file", "")
            continue

        polygon = building_polygon_for_imagery_source(record, source)
        if polygon is None:
            record[f"{source['key']}_aerial_image_url"] = ""
            record[f"{source['key']}_aerial_photo_date"] = ""
            record[f"{source['key']}_aerial_native_resolution"] = ""
            record[f"{source['key']}_aerial_image_file"] = ""
            continue
        bounds = enforce_minimum_export_resolution(padded_bounds(polygon.bounds), source)
        record[f"{source['key']}_aerial_image_url"] = aerial_image_url(source, bounds, polygon)
        metadata = raster_source_metadata(source, polygon)
        record[f"{source['key']}_aerial_photo_date"] = metadata.get("photo_date") or source.get("photo_date", "")
        record[f"{source['key']}_aerial_native_resolution"] = (
            metadata.get("native_resolution") or source.get("native_resolution", "")
        )
        record.setdefault(f"{source['key']}_aerial_image_file", "")
    sync_primary_aerial_fields(record)


def sync_primary_aerial_fields(record: dict) -> None:
    if not IMAGERY_SOURCES:
        return
    successful_sources = [
        source
        for source in IMAGERY_SOURCES
        if str(record.get(f"{source['key']}_aerial_qa_status") or "").lower() == "ok"
        and record.get(f"{source['key']}_aerial_image_file")
    ]
    available_sources = [
        source
        for source in IMAGERY_SOURCES
        if record.get(f"{source['key']}_aerial_image_url")
    ]
    source = (successful_sources or available_sources or IMAGERY_SOURCES)[0]
    key = source["key"]
    record["primary_aerial_source"] = source.get("label") or source.get("name") or key
    record["primary_aerial_image_url"] = record.get(f"{key}_aerial_image_url", "")
    record["primary_aerial_photo_date"] = record.get(f"{key}_aerial_photo_date", "")
    record["primary_aerial_native_resolution"] = record.get(f"{key}_aerial_native_resolution", "")
    record["primary_aerial_image_file"] = record.get(f"{key}_aerial_image_file", "")
    record["primary_aerial_qa_status"] = record.get(f"{key}_aerial_qa_status", "")
    record["primary_aerial_qa_reason"] = record.get(f"{key}_aerial_qa_reason", "")
    record["primary_aerial_qa_blank"] = record.get(f"{key}_aerial_qa_blank", "")
    record["primary_aerial_qa_width"] = record.get(f"{key}_aerial_qa_width", "")
    record["primary_aerial_qa_height"] = record.get(f"{key}_aerial_qa_height", "")
    record["primary_aerial_qa_brightness"] = record.get(f"{key}_aerial_qa_brightness", "")
    record["primary_aerial_qa_contrast"] = record.get(f"{key}_aerial_qa_contrast", "")


def clear_primary_aerial_qa(record: dict) -> None:
    for field, _ in OUTPUT_FIELDS:
        if field.startswith("primary_aerial_qa_"):
            record[field] = ""


def image_qa(path: str | None) -> dict[str, object]:
    if not path or not os.path.exists(path):
        return {
            "status": "missing",
            "reason": "missing",
            "blank": "TRUE",
            "width": "",
            "height": "",
            "brightness": "",
            "contrast": "",
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
                "status": "blank" if blank else "ok",
                "reason": "blank_or_low_contrast" if blank else "",
                "blank": "TRUE" if blank else "FALSE",
                "width": width,
                "height": height,
                "brightness": f"{brightness:.2f}",
                "contrast": f"{contrast:.2f}",
            }
    except OSError as exc:
        return {
            "status": "unreadable",
            "reason": str(exc),
            "blank": "TRUE",
            "width": "",
            "height": "",
            "brightness": "",
            "contrast": "",
        }


def apply_aerial_qa(record: dict, source_key: str, path: str | None) -> None:
    qa = image_qa(path)
    for field, value in qa.items():
        record[f"{source_key}_aerial_qa_{field}"] = value


def web_mercator_tile_indices(bounds: tuple[float, float, float, float], level: int) -> tuple[int, int, int, int, float]:
    minx, miny, maxx, maxy = bounds
    resolution = 156543.03392804097 / (2**level)
    tile_span = 256 * resolution
    origin_x = -20037508.342787
    origin_y = 20037508.342787
    col_min = floor((minx - origin_x) / tile_span)
    col_max = floor((maxx - origin_x) / tile_span)
    row_min = floor((origin_y - maxy) / tile_span)
    row_max = floor((origin_y - miny) / tile_span)
    return col_min, col_max, row_min, row_max, resolution


def fetch_image_tile(service_url: str, level: int, row: int, col: int):
    from PIL import Image

    tile_url = f"{service_url.rstrip('/')}/tile/{level}/{row}/{col}"
    request = Request(tile_url, headers={"User-Agent": "Python Building Collector"})
    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return Image.open(BytesIO(response.read())).convert("RGB")


def save_ai_crop_image(
    record: dict,
    source: dict,
    image_dir: str,
    max_pixels: int,
    buffer_feet: float,
    image_format: str,
) -> str:
    from PIL import Image

    polygon = building_polygon_for_imagery_source(record, source)
    if polygon is None:
        return ""

    bounds = square_buffered_bounds(polygon.bounds, buffer_feet, str(source.get("image_units") or "meters"))
    max_pixels = native_capped_crop_pixels(record, source, bounds, max_pixels)
    source_dir = os.path.join(image_dir, source["key"])
    os.makedirs(source_dir, exist_ok=True)
    base_name = slug(record.get("parcel_number") or record.get("property_address") or record.get("OBJECTID"))
    extension = "webp" if str(image_format).lower() == "webp" else "jpg"
    output_path = os.path.join(source_dir, f"{base_name}-{source['key']}-ai-crop.{extension}")

    if source.get("kind") in ("ImageServer", "MapServer"):
        response_format = "json" if source.get("kind") == "MapServer" else "image"
        crop_url = export_raster_crop_url(source, bounds, max_pixels, image_format, response_format=response_format)
        request = Request(crop_url, headers={"User-Agent": "Python Building Collector"})
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            if response_format == "json":
                payload = json.load(response)
                image_url = payload.get("href")
                if not image_url:
                    raise RuntimeError(f"MapServer export returned no image URL: {payload}")
                image_request = Request(str(image_url), headers={"User-Agent": "Python Building Collector"})
                with urlopen(image_request, timeout=REQUEST_TIMEOUT) as image_response:
                    data = image_response.read()
            else:
                data = response.read()
        with open(output_path, "wb") as handle:
            handle.write(data)
        return output_path

    if source.get("kind") == "DRAPPOriginalTile" and not source.get("crop_tile_service_url"):
        # Current DRCOG archive entries expose original GeoTIFFs but no public
        # tiled crop endpoint. Keep them available for original-tile mode and
        # let another configured imagery source supply the AI crop.
        return ""
    level = int(source.get("crop_tile_level") or AI_CROP_TILE_LEVEL)
    service_url = str(source.get("crop_tile_service_url") or AI_CROP_TILE_SERVICE_URL)
    col_min, col_max, row_min, row_max, resolution = web_mercator_tile_indices(bounds, level)

    cols = range(col_min, col_max + 1)
    rows = range(row_min, row_max + 1)
    mosaic = Image.new("RGB", (len(cols) * 256, len(rows) * 256))
    for row in rows:
        for col in cols:
            tile = fetch_image_tile(service_url, level, row, col)
            mosaic.paste(tile, ((col - col_min) * 256, (row - row_min) * 256))

    minx, miny, maxx, maxy = bounds
    origin_x = -20037508.342787
    origin_y = 20037508.342787
    tile_span = 256 * resolution
    mosaic_minx = origin_x + (col_min * tile_span)
    mosaic_maxy = origin_y - (row_min * tile_span)
    crop_box = (
        max(0, round((minx - mosaic_minx) / resolution)),
        max(0, round((mosaic_maxy - maxy) / resolution)),
        min(mosaic.width, round((maxx - mosaic_minx) / resolution)),
        min(mosaic.height, round((mosaic_maxy - miny) / resolution)),
    )
    crop = mosaic.crop(crop_box)

    max_pixels = int(max_pixels or AI_CROP_PIXELS)
    if max(crop.size) > max_pixels:
        crop.thumbnail((max_pixels, max_pixels), Image.Resampling.LANCZOS)

    save_kwargs = {"quality": 88}
    crop.save(output_path, "WEBP" if extension == "webp" else "JPEG", **save_kwargs)
    return output_path


def download_original_tile_images(record: dict, image_dir: str) -> None:
    os.makedirs(image_dir, exist_ok=True)
    base_name = slug(record.get("parcel_number") or record.get("property_address") or record.get("OBJECTID"))
    for source in IMAGERY_SOURCES:
        key = source["key"]
        url = record.get(f"{key}_aerial_image_url")
        if not url:
            apply_aerial_qa(record, key, None)
            continue
        source_dir = os.path.join(image_dir, key)
        os.makedirs(source_dir, exist_ok=True)
        remote_name = unquote(os.path.basename(urlparse(str(url)).path))
        if not remote_name or "." not in remote_name:
            remote_name = f"{base_name}-{key}.img"
        output_path = os.path.join(source_dir, remote_name)
        if not os.path.exists(output_path):
            try:
                request = Request(str(url), headers={"User-Agent": "Python Building Collector"})
                with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                    data = response.read()
                with open(output_path, "wb") as handle:
                    handle.write(data)
            except Exception as exc:
                print(f"  Warning: failed to download {source['name']} image for {base_name}: {exc}")
                apply_aerial_qa(record, key, None)
                continue
        record[f"{key}_aerial_image_file"] = output_path
        apply_aerial_qa(record, key, output_path)
    sync_primary_aerial_fields(record)


def download_aerial_images(
    record: dict,
    image_dir: str,
    image_mode: str = "ai-crop",
    image_pixels: int = AI_CROP_PIXELS,
    image_buffer_feet: float = AI_CROP_BUFFER_FEET,
    image_format: str = AI_CROP_FORMAT,
) -> None:
    if image_mode == "original-tile":
        download_original_tile_images(record, image_dir)
        return

    os.makedirs(image_dir, exist_ok=True)
    for source in IMAGERY_SOURCES:
        key = source["key"]
        if not record.get(f"{key}_aerial_image_url"):
            apply_aerial_qa(record, key, None)
            continue
        try:
            output_path = save_ai_crop_image(
                record,
                source,
                image_dir,
                image_pixels,
                image_buffer_feet,
                image_format,
            )
        except Exception as exc:
            base_name = slug(record.get("parcel_number") or record.get("property_address") or record.get("OBJECTID"))
            print(f"  Warning: failed to create {source['name']} AI crop for {base_name}: {exc}")
            apply_aerial_qa(record, key, None)
            continue
        record[f"{key}_aerial_image_file"] = output_path
        apply_aerial_qa(record, key, output_path)
    sync_primary_aerial_fields(record)


def combine_data(buildings: list[dict], parcels: list[dict]) -> list[dict]:
    """Combine building and parcel data using spatial join."""
    print("Building spatial index...")
    # Build aligned lists so STRtree indices map directly to valid_parcels
    parcel_polygons = []
    valid_parcels: list[dict] = []
    for parcel in parcels:
        parcel_poly = get_parcel_polygon(parcel)
        if parcel_poly is None:
            continue
        parcel_polygons.append(parcel_poly)
        valid_parcels.append(parcel)

    parcel_index = STRtree(parcel_polygons) if parcel_polygons else None

    combined = []
    skipped = 0
    matched = 0
    print("Matching buildings...")
    for building in buildings:
        building_poly = get_building_polygon(building)
        if building_poly is None:
            skipped += 1
            continue
        stored_footprint_sqft = numeric_value(building.get("footprint_sqft"))
        area_sqft = stored_footprint_sqft if stored_footprint_sqft and stored_footprint_sqft > 0 else building_poly.area
        building["projected_building_footprint_area"] = area_sqft
        building["projected_roof_area"] = area_sqft

        parcel = None
        if parcel_index is not None:
            parcel = match_building_to_parcel(building_poly, parcel_index, parcel_polygons, valid_parcels)

        if parcel:
            merged = {**building, **parcel}
            matched += 1
        else:
            merged = building

        combined.append(merged)

    print(f"Matched {matched} buildings to parcels, skipped {skipped} invalid building geometries")
    print("Calculating roof metrics...")
    for record in combined:
        record["roof_area_est"] = calculate_roof_area_est(record)
        record["roof_squares"] = calculate_roof_squares(record)
        add_output_fields(record)

    def sort_key(record: dict):
        try:
            rs = float(record.get("roof_squares", 0) or 0)
        except (TypeError, ValueError):
            rs = 0
        return rs

    return sorted(combined, key=sort_key, reverse=True)
