#!/usr/bin/env python3
"""Collect buildings with parcel and address information."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import date
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

from assessor_detail import canonical_report_values, fetch_assessor_details
from county_config import assessor_sources, county_profile

# TODO: integrate NOAA hail exposure data
# TODO: integrate permit history for recent roof work
# TODO: integrate historical imagery to detect roof condition changes
# TODO: integrate AI roof condition analysis and water damage / insurance indicators

DEFAULT_PROFILE = county_profile("denver")
DENVER_BUILDINGS_URL = DEFAULT_PROFILE.building_url
PARCELS_URL = DEFAULT_PROFILE.parcel_url

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

PARCEL_CACHE_EXTRA_FIELDS = [
    "parcel_shape_area",
    "parcel_geometry",
    "full_parcel_number",
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
    ("denver_gis_aerial_image_url", "Denver GIS Aerial Image URL"),
    ("denver_gis_aerial_photo_date", "Denver GIS Aerial Photo Date"),
    ("denver_gis_aerial_image_file", "Denver GIS Aerial Image File"),
]

IMAGERY_SOURCES = list(DEFAULT_PROFILE.imagery_sources)
ACTIVE_COUNTY_NAME = DEFAULT_PROFILE.display_name.replace(" County", "")
ACTIVE_STATE = "CO"


BUILDING_CRS = None
PARCEL_CRS = None
TRANSFORMER_TO_PARCEL = None
TRANSFORMER_TO_BUILDING = None
TRANSFORMER_TO_IMAGE = None
TRANSFORMER_TO_DRCOG_TILE = None
BUILDING_SOURCE_KIND = "arcgis"


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
    url = url or DENVER_BUILDINGS_URL
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


def parcel_cache_fields() -> list[str]:
    return collect_parcel_fields(PARCELS_URL) + PARCEL_CACHE_EXTRA_FIELDS


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def write_parcel_cache(parcels: list[dict], output_path: str) -> None:
    ensure_parent_dir(output_path)
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=parcel_cache_fields())
        writer.writeheader()
        for parcel in parcels:
            writer.writerow({field: parcel.get(field, "") for field in parcel_cache_fields()})


def read_parcel_cache(input_path: str) -> list[dict]:
    csv.field_size_limit(sys.maxsize)
    with open(input_path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_or_collect_parcels(
    cache_path: str,
    fetch_limit: int | None = None,
    refresh_cache: bool = False,
    where: str = "1=1",
) -> list[dict]:
    if os.path.exists(cache_path) and not refresh_cache:
        print(f"Loading parcels from cache: {cache_path}")
        parcels = read_parcel_cache(cache_path)
        if fetch_limit:
            return parcels[:fetch_limit]
        return parcels

    print("Loading parcels from ArcGIS...")
    parcels = collect_parcels(fetch_limit, where=where)
    print(f"Writing parcel cache: {cache_path}")
    write_parcel_cache(parcels, cache_path)
    return parcels


def parse_zip_codes(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        zip_code[:5]
        for zip_code in (normalize_zip(piece) for piece in re.split(r"[,\\s]+", value))
        if zip_code
    }


def zip_slug(zip_codes: set[str]) -> str:
    if not zip_codes:
        return "all"
    return "-".join(sorted(zip_codes))


def default_run_paths(script_dir: str, state: str, county_key: str, county_name: str, zip_codes: set[str]) -> tuple[str, str]:
    state_part = (state or "CO").strip().upper()
    county_part = county_name.replace(" County", "").replace(" ", "")
    slug_part = zip_slug(zip_codes)
    parcels_dir = os.path.join(script_dir, "data", state_part, county_part, "parcels")
    output_name = f"{county_key}_{slug_part}_buildings_with_parcels.csv"
    cache_name = f"{county_key}_{slug_part}_parcel_data.csv"
    return os.path.join(parcels_dir, output_name), os.path.join(parcels_dir, cache_name)


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


def assessor_zip(record: dict) -> str:
    for field in ("SITUS_ZIP", "SITE_ZIP", "PROPERTY_ZIP", "PROP_ZIP", "ZIPCODE", "ZIP_CODE"):
        zip_code = normalize_zip(record.get(field))
        if zip_code:
            return zip_code
    return ""


def filter_parcels_by_zip(parcels: list[dict], zip_codes: set[str]) -> list[dict]:
    if not zip_codes:
        return parcels
    return [parcel for parcel in parcels if parcel_zip(parcel) in zip_codes]


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
    if BUILDING_SOURCE_KIND == "postgis":
        if not geometry:
            raise ValueError("PostGIS building discovery requires a selected geometry envelope")
        from building_footprint_store import collect_buildings_in_envelope

        return collect_buildings_in_envelope(ACTIVE_COUNTY_NAME, geometry, fetch_limit)
    offset = 0
    results: list[dict] = []
    while True:
        features = collect_building_page(offset, geometry)
        if not features:
            break
        results.extend(features)
        if fetch_limit and len(results) >= fetch_limit:
            return results[:fetch_limit]
        offset += PAGE_SIZE
        if len(features) < PAGE_SIZE:
            break
    return results


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
    if BUILDING_SOURCE_KIND != "postgis" or not DENVER_BUILDINGS_URL:
        return []
    if not geometry:
        raise ValueError("Secondary building discovery requires a selected geometry envelope")
    row_limit = min(int(fetch_limit or 10_000), 10_000)
    offset = 0
    records: list[dict] = []
    fields = collect_available_fields(
        DENVER_BUILDINGS_URL, BUILDING_FIELDS + OPTIONAL_BUILDING_FIELDS
    )
    oid_field = _LAYER_OID_FIELDS.get(DENVER_BUILDINGS_URL)
    if not oid_field:
        metadata = fetch_json(layer_metadata_url(DENVER_BUILDINGS_URL)) or {}
        oid_field = str(
            metadata.get("objectIdField")
            or metadata.get("objectIdFieldName")
            or "OBJECTID"
        )
        _LAYER_OID_FIELDS[DENVER_BUILDINGS_URL] = oid_field
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
        page = fetch_arcgis_json(DENVER_BUILDINGS_URL + "?" + urlencode(params))
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
    difference = abs(float(primary_area) - secondary_area) / max(float(primary_area), 1.0)
    return {
        "status": "validated" if difference <= tolerance else "discrepancy",
        "primary_sqft": round(float(primary_area), 1),
        "secondary_sqft": round(secondary_area, 1),
        "difference_pct": round(difference * 100, 2),
        "overlap_pct": round(best[0] * 100, 2),
        "tolerance_pct": round(tolerance * 100, 2),
    }


def collect_building_page(offset: int, geometry: str | None = None) -> list[dict]:
    """Fetch one page of buildings, optionally constrained by a geometry filter."""
    where = "1=1"
    building_fields = collect_building_fields(DENVER_BUILDINGS_URL)
    order_field = "objectid" if "objectid" in building_fields else "OBJECTID"
    params = {
        "where": where,
        "outFields": ",".join(building_fields),
        "returnGeometry": "true",
        "f": "json",
        "resultOffset": offset,
        "resultRecordCount": PAGE_SIZE,
        "orderByFields": f"{order_field} ASC",
    }
    if geometry:
        params["geometry"] = geometry
        params["geometryType"] = "esriGeometryEnvelope"
        params["spatialRel"] = "esriSpatialRelIntersects"
        params["inSR"] = str(BUILDING_CRS)
        params["outSR"] = str(BUILDING_CRS)

    full_url = DENVER_BUILDINGS_URL + "?" + urlencode(params)
    try:
        page = fetch_arcgis_json(full_url)
    except Exception as exc:
        raise RuntimeError(f"Error fetching buildings: {exc}") from exc

    results: list[dict] = []
    for feature in page.get("features", []):
        attrs = feature.get("attributes", {})
        attrs["building_shape_area"] = attrs.get("Shape__Area") or attrs.get("SHAPE__Area")
        attrs["building_esri_geometry"] = feature.get("geometry")
        attrs["building_geometry"] = geometry_to_wkt(feature.get("geometry"))
        attrs["year_built"] = ""
        attrs["effective_year_built"] = ""
        results.append(attrs)
    return results


def collect_parcels(fetch_limit: int | None = None, where: str = "1=1") -> list[dict]:
    """Fetch assessor parcel polygons."""
    offset = 0
    results: list[dict] = []
    while True:
        page = fetch_page(PARCELS_URL, where, offset, collect_parcel_fields(PARCELS_URL), return_geometry=True)
        features = page.get("features", [])
        if not features:
            break
        for feature in features:
            attrs = feature.get("attributes", {})
            attrs["parcel_shape_area"] = attrs.get("Shape__Area")
            attrs["parcel_geometry"] = geometry_to_wkt(feature.get("geometry"))
            attrs["full_parcel_number"] = parcel_join_key(attrs)
            results.append(attrs)
            if fetch_limit and len(results) >= fetch_limit:
                return results[:fetch_limit]
        offset += PAGE_SIZE
        if len(features) < PAGE_SIZE:
            break
    return results


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
    if ACTIVE_COUNTY_NAME.strip().lower() == "denver":
        schedule = normalize_key(record.get("SCHEDNUM") or record.get("PARID"))
        if schedule:
            return schedule
    for field in (
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


def building_age_year(record: dict) -> int | None:
    value = first_nonempty(record, ("effective_year_built", "year_built"))
    try:
        year = int(float(value))
    except (TypeError, ValueError):
        return None
    if year <= 0:
        return None
    return year


def is_at_least_20_years_old(record: dict, current_year: int | None = None) -> bool:
    year = building_age_year(record)
    if year is None:
        return True
    return (current_year or date.today().year) - year >= 20


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


def is_residential_property(record: dict) -> bool:
    text = " ".join(
        str(record.get(field) or "")
        for field in ("property_class", "PROPERTY_CLASS_DESC", "D_CLASS_CN", "property_use")
    ).lower()
    return any(term in text for term in RESIDENTIAL_TERMS)


def has_parcel_match(record: dict) -> bool:
    return bool(parcel_join_key(record))


def has_property_address(record: dict) -> bool:
    return bool(address_from_record(record))


def backfill_missing_parcel_fields(record: dict, parcel_lookup: dict[str, dict]) -> None:
    parcel = parcel_lookup.get(parcel_join_key(record))
    if not parcel:
        return
    for field, value in parcel.items():
        if value in (None, ""):
            continue
        if record.get(field) in (None, ""):
            record[field] = value


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


ASSESSOR_OUTPUT_FIELDS = {
    "Year Built": "year_built",
    "Effective Year Built": "effective_year_built",
    "Property Use": "property_use",
    "Stories": "stories",
    "Construction Type": "construction_type",
    "Land Value": "land_value",
}


def enrich_with_assessor(records: list[dict], county: str) -> None:
    """Enrich matched buildings with exact, parcel-scoped assessor requests."""
    records_by_parcel: dict[str, list[dict]] = {}
    for record in records:
        parcel_id = parcel_join_key(record)
        if parcel_id:
            records_by_parcel.setdefault(parcel_id, []).append(record)

    matched = 0
    warning_count = 0
    for parcel_id, parcel_records in records_by_parcel.items():
        result = fetch_assessor_details(county, [parcel_id])
        values = canonical_report_values(result.records)
        warning_count += len(result.warnings)
        if not values:
            continue
        for record in parcel_records:
            for report_field, value in values.items():
                output_field = ASSESSOR_OUTPUT_FIELDS.get(report_field)
                if output_field and record.get(output_field) in (None, "", 0, "0"):
                    record[output_field] = value
            record["_assessor_source_counts"] = dict(result.source_counts)
            record["_assessor_warnings"] = list(result.warnings)
            matched += 1
    print(
        f"Matched {matched} records using {len(records_by_parcel)} bounded assessor lookups"
        + (f" ({warning_count} service warnings)" if warning_count else "")
    )


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


def write_csv(records: list[dict], output_path: str) -> None:
    """Write records to CSV with selected fields."""
    headers = [label for _, label in OUTPUT_FIELDS]
    ensure_parent_dir(output_path)
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for record in records:
            writer.writerow({label: record.get(field, "") for field, label in OUTPUT_FIELDS})


def write_filtered_csv(
    records: Iterable[dict],
    output_path: str,
    min_squares: float,
    batch_size: int = 10,
    max_output_records: int | None = None,
    download_images: bool = False,
    image_dir: str | None = None,
    image_mode: str = "ai-crop",
    image_pixels: int = AI_CROP_PIXELS,
    image_buffer_feet: float = AI_CROP_BUFFER_FEET,
    image_format: str = AI_CROP_FORMAT,
) -> dict:
    """Filter and write output records, flushing every batch_size rows."""
    headers = [label for _, label in OUTPUT_FIELDS]
    counts = {
        "roof_squares": 0,
        "age": 0,
        "parcel": 0,
        "residential": 0,
        "low_slope": 0,
        "written": 0,
    }

    def above_roof_square_threshold(record: dict) -> bool:
        try:
            return float(record.get("roof_squares", 0) or 0) > min_squares
        except (TypeError, ValueError):
            return False

    pending = 0
    ensure_parent_dir(output_path)
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        handle.flush()

        for record in records:
            add_output_fields(record)

            if not above_roof_square_threshold(record):
                counts["roof_squares"] += 1
                continue
            if not is_at_least_20_years_old(record):
                counts["age"] += 1
                continue
            if not has_parcel_match(record):
                counts["parcel"] += 1
                continue
            if is_residential_property(record):
                counts["residential"] += 1
                continue
            if record.get("likely_low_slope") != "TRUE":
                counts["low_slope"] += 1
                continue

            add_aerial_image_fields(record)

            if download_images and image_dir:
                try:
                    download_aerial_images(
                        record,
                        image_dir,
                        image_mode=image_mode,
                        image_pixels=image_pixels,
                        image_buffer_feet=image_buffer_feet,
                        image_format=image_format,
                    )
                except Exception as exc:
                    print(f"  Warning: failed to download aerial images for {record.get('parcel_number')}: {exc}")
                    clear_primary_aerial_qa(record)
            else:
                clear_primary_aerial_qa(record)

            writer.writerow({label: record.get(field, "") for field, label in OUTPUT_FIELDS})
            counts["written"] += 1
            pending += 1

            if max_output_records and counts["written"] >= max_output_records:
                break

            if pending >= batch_size:
                handle.flush()
                print(f"  Wrote {counts['written']} records...")
                pending = 0

        handle.flush()

    return counts


def write_filtered_csv_streaming(
    parcels: list[dict],
    output_path: str,
    min_squares: float,
    geometry: str | None,
    max_output_records: int,
    download_images: bool = False,
    image_dir: str | None = None,
    image_mode: str = "ai-crop",
    image_pixels: int = AI_CROP_PIXELS,
    image_buffer_feet: float = AI_CROP_BUFFER_FEET,
    image_format: str = AI_CROP_FORMAT,
) -> dict:
    """Fetch building pages, spatially join, filter, and stop once enough rows are written."""
    headers = [label for _, label in OUTPUT_FIELDS]
    counts = {
        "roof_squares": 0,
        "age": 0,
        "parcel": 0,
        "residential": 0,
        "low_slope": 0,
        "written": 0,
        "building_pages": 0,
        "buildings_seen": 0,
    }

    def above_roof_square_threshold(record: dict) -> bool:
        try:
            return float(record.get("roof_squares", 0) or 0) > min_squares
        except (TypeError, ValueError):
            return False

    ensure_parent_dir(output_path)
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        handle.flush()

        offset = 0
        while counts["written"] < max_output_records:
            buildings = collect_building_page(offset, geometry)
            if not buildings:
                break
            counts["building_pages"] += 1
            counts["buildings_seen"] += len(buildings)
            print(f"  Scanning building page {counts['building_pages']} ({counts['buildings_seen']} buildings seen)...")
            combined = combine_data(buildings, parcels)
            for record in combined:
                add_output_fields(record)

                if not above_roof_square_threshold(record):
                    counts["roof_squares"] += 1
                    continue
                if not is_at_least_20_years_old(record):
                    counts["age"] += 1
                    continue
                if not has_parcel_match(record):
                    counts["parcel"] += 1
                    continue
                if is_residential_property(record):
                    counts["residential"] += 1
                    continue
                if record.get("likely_low_slope") != "TRUE":
                    counts["low_slope"] += 1
                    continue

                add_aerial_image_fields(record)

                if download_images and image_dir:
                    try:
                        download_aerial_images(
                            record,
                            image_dir,
                            image_mode=image_mode,
                            image_pixels=image_pixels,
                            image_buffer_feet=image_buffer_feet,
                            image_format=image_format,
                        )
                    except Exception as exc:
                        print(f"  Warning: failed to download aerial images for {record.get('parcel_number')}: {exc}")
                        clear_primary_aerial_qa(record)
                else:
                    clear_primary_aerial_qa(record)

                writer.writerow({label: record.get(field, "") for field, label in OUTPUT_FIELDS})
                counts["written"] += 1
                if counts["written"] >= max_output_records:
                    break

            handle.flush()
            if len(buildings) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

    return counts


def parcel_bounds_in_building_crs(parcel: dict, padding: float = 25.0) -> str | None:
    polygon = get_parcel_polygon(parcel)
    if polygon is None:
        return None
    if TRANSFORMER_TO_BUILDING is not None:
        polygon = transform(TRANSFORMER_TO_BUILDING.transform, polygon)
    if polygon.is_empty:
        return None
    minx, miny, maxx, maxy = polygon.bounds
    return f"{minx - padding},{miny - padding},{maxx + padding},{maxy + padding}"


def write_filtered_csv_by_parcel_scan(
    parcels: list[dict],
    output_path: str,
    min_squares: float,
    max_output_records: int,
    download_images: bool = False,
    image_dir: str | None = None,
    image_mode: str = "ai-crop",
    image_pixels: int = AI_CROP_PIXELS,
    image_buffer_feet: float = AI_CROP_BUFFER_FEET,
    image_format: str = AI_CROP_FORMAT,
) -> dict:
    """Query roofprints around individual parcels until enough eligible rows are written."""
    headers = [label for _, label in OUTPUT_FIELDS]
    counts = {
        "roof_squares": 0,
        "age": 0,
        "parcel": 0,
        "residential": 0,
        "low_slope": 0,
        "address": 0,
        "written": 0,
        "parcels_scanned": 0,
        "building_queries": 0,
        "buildings_seen": 0,
    }
    seen_buildings: set[str] = set()
    written_parcels: set[str] = set()
    parcel_lookup = {
        parcel_join_key(parcel): parcel
        for parcel in parcels
        if parcel_join_key(parcel)
    }

    def above_roof_square_threshold(record: dict) -> bool:
        try:
            return float(record.get("roof_squares", 0) or 0) > min_squares
        except (TypeError, ValueError):
            return False

    scan_parcels = []
    for parcel in parcels:
        add_output_fields(parcel)
        if is_residential_property(parcel):
            continue
        scan_parcels.append(parcel)

    def parcel_area(parcel: dict) -> float:
        try:
            return float(parcel.get("parcel_shape_area") or parcel.get("Shape__Area") or 0)
        except (TypeError, ValueError):
            return 0.0

    scan_parcels.sort(key=parcel_area, reverse=True)

    ensure_parent_dir(output_path)
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        handle.flush()

        for parcel in scan_parcels:
            if counts["written"] >= max_output_records:
                break
            geometry = parcel_bounds_in_building_crs(parcel)
            if not geometry:
                continue
            counts["parcels_scanned"] += 1
            buildings = collect_building_page(0, geometry)
            counts["building_queries"] += 1
            counts["buildings_seen"] += len(buildings)
            if not buildings:
                continue

            unique_buildings = []
            for building in buildings:
                building_id = normalize_key(building.get("OBJECTID") or building.get("objectid") or building.get("building_geometry"))
                if building_id in seen_buildings:
                    continue
                seen_buildings.add(building_id)
                unique_buildings.append(building)

            combined = combine_data(unique_buildings, [parcel])
            for record in combined:
                backfill_missing_parcel_fields(record, parcel_lookup)
                add_output_fields(record)
                parcel_key = parcel_join_key(record)
                if parcel_key in written_parcels:
                    continue

                if not above_roof_square_threshold(record):
                    counts["roof_squares"] += 1
                    continue
                if not is_at_least_20_years_old(record):
                    counts["age"] += 1
                    continue
                if not has_parcel_match(record):
                    counts["parcel"] += 1
                    continue
                if not has_property_address(record):
                    counts["address"] += 1
                    continue
                if is_residential_property(record):
                    counts["residential"] += 1
                    continue
                if record.get("likely_low_slope") != "TRUE":
                    counts["low_slope"] += 1
                    continue

                add_aerial_image_fields(record)

                if download_images and image_dir:
                    try:
                        download_aerial_images(
                            record,
                            image_dir,
                            image_mode=image_mode,
                            image_pixels=image_pixels,
                            image_buffer_feet=image_buffer_feet,
                            image_format=image_format,
                        )
                    except Exception as exc:
                        print(f"  Warning: failed to download aerial images for {record.get('parcel_number')}: {exc}")
                        clear_primary_aerial_qa(record)
                else:
                    clear_primary_aerial_qa(record)

                writer.writerow({label: record.get(field, "") for field, label in OUTPUT_FIELDS})
                counts["written"] += 1
                if parcel_key:
                    written_parcels.add(parcel_key)
                if counts["written"] >= max_output_records:
                    break

            handle.flush()
            if counts["parcels_scanned"] % 25 == 0:
                print(
                    f"  Parcel scan checked {counts['parcels_scanned']} parcels, "
                    f"saw {counts['buildings_seen']} buildings, wrote {counts['written']} rows..."
                )

    return counts


def parse_args() -> argparse.Namespace:
    script_dir = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser(
        description="Collect buildings with parcel and address information."
    )
    parser.add_argument("--county", default="denver", help="County profile key")
    parser.add_argument("--state", default="CO", help="Two-letter state code used in data/output folders")
    parser.add_argument("--output", default=None, help="CSV output file path")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of building records to collect")
    parser.add_argument("--list-fields", action="store_true", help="Print available collected fields and exit")
    parser.add_argument("--min-squares", type=float, default=50.0, help="Strict roofing squares threshold for output")
    parser.add_argument("--max-output-records", type=int, default=None, help="Stop after writing this many output rows")
    parser.add_argument("--parcel-scan-buildings", action="store_true", help="Query roofprints around individual parcels instead of the full ZIP envelope")
    parser.add_argument("--parcel-limit", type=int, default=None, help="Maximum parcel records to collect; intended for smoke tests")
    parser.add_argument("--parcel-cache", default=None, help="CSV cache for parcel data")
    parser.add_argument("--refresh-parcel-cache", action="store_true", help="Recreate the parcel cache even when it already exists")
    parser.add_argument("--zip-codes", default=None, help="Comma or space separated ZIP codes used to filter cached parcel data")
    parser.add_argument("--skip-assessor", action="store_true", help="Skip assessor table enrichment")
    parser.add_argument(
        "--download-aerial-images",
        action="store_true",
        help="Download aerial image files for rows written to the CSV",
    )
    parser.add_argument(
        "--image-dir",
        default=None,
        help="Directory for downloaded aerial images; defaults to an aerial_images folder next to the output CSV",
    )
    parser.add_argument(
        "--image-mode",
        choices=("ai-crop", "original-tile"),
        default="ai-crop",
        help="Store compact AI-ready crops by default; use original-tile to download full source GeoTIFFs",
    )
    parser.add_argument(
        "--image-pixels",
        type=int,
        default=AI_CROP_PIXELS,
        help="Maximum width/height for AI crop images",
    )
    parser.add_argument(
        "--image-buffer-feet",
        type=float,
        default=AI_CROP_BUFFER_FEET,
        help="Building footprint buffer included around AI crops",
    )
    parser.add_argument(
        "--image-format",
        choices=("jpg", "webp"),
        default=AI_CROP_FORMAT,
        help="Output format for AI crop images",
    )
    return parser.parse_args()


def main() -> int:
    global DENVER_BUILDINGS_URL, PARCELS_URL, IMAGERY_SOURCES, _COLLECT_PARCEL_FIELDS, _COLLECT_BUILDING_FIELDS, ACTIVE_COUNTY_NAME, ACTIVE_STATE, BUILDING_SOURCE_KIND
    args = parse_args()
    profile = county_profile(args.county)
    script_dir = os.path.dirname(os.path.abspath(__file__))

    DENVER_BUILDINGS_URL = profile.building_url
    PARCELS_URL = profile.parcel_url
    IMAGERY_SOURCES = list(profile.imagery_sources)
    BUILDING_SOURCE_KIND = profile.building_source
    ACTIVE_COUNTY_NAME = profile.display_name.replace(" County", "")
    ACTIVE_STATE = (args.state or "CO").strip().upper()
    _COLLECT_PARCEL_FIELDS = None
    _COLLECT_BUILDING_FIELDS = None
    args.zip_codes = args.zip_codes if args.zip_codes is not None else profile.default_zip_codes
    zip_codes = parse_zip_codes(args.zip_codes)
    default_output, default_parcel_cache = default_run_paths(
        script_dir,
        ACTIVE_STATE,
        profile.key,
        profile.display_name,
        zip_codes,
    )
    args.output = args.output or default_output
    args.parcel_cache = args.parcel_cache or default_parcel_cache
    
    if args.list_fields:
        print("Collected fields:")
        for _, label in OUTPUT_FIELDS:
            print("-", label)
        return 0

    init_crs_transformers(DENVER_BUILDINGS_URL, PARCELS_URL, profile.building_crs)

    if zip_codes:
        print(f"Filtering parcel and assessor data to ZIP codes: {', '.join(sorted(zip_codes))}")

    print("Loading parcels...")
    parcel_where = parcel_zip_where(zip_codes)
    all_parcels = load_or_collect_parcels(
        args.parcel_cache,
        fetch_limit=args.parcel_limit,
        refresh_cache=args.refresh_parcel_cache,
        where=parcel_where,
    )
    print(f"  Found {len(all_parcels)} parcels before ZIP filtering")
    parcels = filter_parcels_by_zip(all_parcels, zip_codes)
    print(f"  Using {len(parcels)} parcels after ZIP filtering")

    if not parcels:
        print("No parcels matched the requested ZIP codes; writing empty output.")
        write_csv([], args.output)
        print(f"Saved results to {args.output}")
        return 0

    parcel_geometry = get_parcel_bounds_in_building_crs(parcels)
    if parcel_geometry:
        print(f"Fetching buildings inside parcel envelope: {parcel_geometry}")
    else:
        print("Parcel envelope not available; fetching all buildings")

    min_sq = float(args.min_squares if args.min_squares is not None else 50)
    image_dir = args.image_dir or os.path.join(os.path.dirname(os.path.abspath(args.output)), "aerial_images")
    if args.parcel_scan_buildings and args.max_output_records and not assessor_sources(profile.key):
        print("Scanning individual parcels until enough filtered output rows are written...")
        counts = write_filtered_csv_by_parcel_scan(
            parcels,
            args.output,
            min_sq,
            args.max_output_records,
            download_images=args.download_aerial_images,
            image_dir=image_dir,
            image_mode=args.image_mode,
            image_pixels=args.image_pixels,
            image_buffer_feet=args.image_buffer_feet,
            image_format=args.image_format,
        )
        print(
            f"Scanned {counts['parcels_scanned']} parcels with {counts['building_queries']} building queries; "
            f"saw {counts['buildings_seen']} buildings; "
            f"filtered {counts['roof_squares']} records with roof_squares <= {min_sq}, "
            f"{counts['age']} records less than 20 years old, "
            f"{counts['parcel']} records without parcel matches, "
            f"{counts['residential']} residential records, "
            f"{counts['low_slope']} records with likely_low_slope false; "
            f"wrote {counts['written']} records"
        )
        print(f"Saved results to {args.output}")
        return 0

    if args.max_output_records and not assessor_sources(profile.key) and not args.limit:
        print("Streaming buildings until enough filtered output rows are written...")
        counts = write_filtered_csv_streaming(
            parcels,
            args.output,
            min_sq,
            parcel_geometry,
            args.max_output_records,
            download_images=args.download_aerial_images,
            image_dir=image_dir,
            image_mode=args.image_mode,
            image_pixels=args.image_pixels,
            image_buffer_feet=args.image_buffer_feet,
            image_format=args.image_format,
        )
        print(
            f"Scanned {counts['buildings_seen']} buildings across {counts['building_pages']} pages; "
            f"filtered {counts['roof_squares']} records with roof_squares <= {min_sq}, "
            f"{counts['age']} records less than 20 years old, "
            f"{counts['parcel']} records without parcel matches, "
            f"{counts['residential']} residential records, "
            f"{counts['low_slope']} records with likely_low_slope false; "
            f"wrote {counts['written']} records"
        )
        print(f"Saved results to {args.output}")
        return 0

    print("Loading buildings...")
    buildings = collect_buildings(args.limit, parcel_geometry)
    print(f"  Found {len(buildings)} buildings")

    print("Performing spatial join...")
    combined = combine_data(buildings, parcels)

    if not args.skip_assessor:
        if assessor_sources(profile.key):
            print("Loading bounded assessor details for matched parcels...")
            enrich_with_assessor(combined, profile.key)
        else:
            print(f"Skipping assessor enrichment; {profile.display_name} has no assessor source configured.")

    print("Writing CSV...")
    counts = write_filtered_csv(
        combined,
        args.output,
        min_sq,
        batch_size=10,
        max_output_records=args.max_output_records,
        download_images=args.download_aerial_images,
        image_dir=image_dir,
        image_mode=args.image_mode,
        image_pixels=args.image_pixels,
        image_buffer_feet=args.image_buffer_feet,
        image_format=args.image_format,
    )
    print(
        f"Filtered {counts['roof_squares']} records with roof_squares <= {min_sq}, "
        f"{counts['age']} records less than 20 years old, "
        f"{counts['parcel']} records without parcel matches, "
        f"{counts['residential']} residential records, "
        f"{counts['low_slope']} records with likely_low_slope false; "
        f"wrote {counts['written']} records"
    )

    print(f"Saved results to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
