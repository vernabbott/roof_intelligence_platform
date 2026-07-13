#!/usr/bin/env python3
"""County and imagery source configuration for roof intelligence data collection."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CountyProfile:
    key: str
    display_name: str
    building_url: str
    parcel_url: str
    assessor_url: str | None
    default_zip_codes: str
    default_output_name: str
    default_parcel_cache_name: str
    imagery_sources: tuple[dict, ...]


DENVER_BUILDINGS_URL = (
    "https://services2.arcgis.com/lNLIDd8Pw9GneaXl/arcgis/rest/services/"
    "City_of_Denver_All_Building_Outlines/FeatureServer/0/query"
)

DENVER_PARCELS_URL = (
    "https://services1.arcgis.com/zdB7qR0BtYrg0Xpl/arcgis/rest/services/"
    "ODC_PROP_PARCELS_A/FeatureServer/245/query"
)

DENVER_ASSESSOR_URL = (
    "https://services1.arcgis.com/zdB7qR0BtYrg0Xpl/arcgis/rest/services/"
    "ODC_real_property_apartment_and_commercial_characteristics/FeatureServer/58/query"
)

ARAPAHOE_BUILDINGS_URL = (
    "https://gis.arapahoegov.com/arcgis/rest/services/"
    "CountyFeatureService/FeatureServer/34/query"
)

ARAPAHOE_PARCELS_URL = (
    "https://gis.arapahoegov.com/arcgis/rest/services/"
    "CountyFeatureService/FeatureServer/14/query"
)

JEFFERSON_BUILDINGS_URL = (
    "https://gisportal.jeffco.us/server/rest/services/Hosted/"
    "Building_Roofprint_Static_2022/FeatureServer/7/query"
)

JEFFERSON_PARCELS_URL = (
    "https://gisportal.jeffco.us/server2/rest/services/"
    "Parcel/FeatureServer/20/query"
)

ADAMS_BUILDINGS_URL = (
    "https://services3.arcgis.com/4PNQOtAivErR7nbT/arcgis/rest/services/"
    "Building_Footprints/FeatureServer/0/query"
)

ADAMS_PARCELS_URL = (
    "https://services3.arcgis.com/4PNQOtAivErR7nbT/arcgis/rest/services/"
    "Parcels/FeatureServer/0/query"
)

DENVER_IMAGERY_SOURCES = (
    {
        "key": "denver_gis",
        "name": "Denver GIS DRAPP 2018 original tile",
        "label": "Denver GIS",
        "kind": "DRAPPOriginalTile",
        "index_url": "https://gis.drcog.org/server/rest/services/RDC/TIFF_2018_INDEX/MapServer/0",
        "url_field": "tif_link",
        "date_field": "photo_date",
        "archive_base_url": "https://drapparchive.s3.us-east-2.amazonaws.com",
    },
)

ARAPAHOE_IMAGERY_SOURCES = (
    {
        "key": "arapahoe_aerials",
        "name": "Arapahoe County 2024 aerial ImageServer",
        "label": "Arapahoe County Aerials",
        "kind": "ImageServer",
        "url": "https://gis.arapahoegov.com/arcgis/rest/services/Aerials/ImageServer",
        "image_crs": 2232,
        "image_units": "feet",
        "photo_date": "20240301",
    },
)

JEFFERSON_IMAGERY_SOURCES = (
    {
        "key": "world_imagery",
        "name": "Esri World Imagery MapServer",
        "label": "Esri World Imagery",
        "kind": "MapServer",
        "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer",
        "image_crs": 3857,
        "image_units": "meters",
        "max_export_pixels": 1024,
        "metadata_layer": 0,
        "metadata_date_field": "SRC_DATE",
        "photo_date": "",
    },
)

ADAMS_IMAGERY_SOURCES = (
    {
        "key": "world_imagery",
        "name": "Esri World Imagery MapServer",
        "label": "Esri World Imagery",
        "kind": "MapServer",
        "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer",
        "image_crs": 3857,
        "image_units": "meters",
        "max_export_pixels": 1024,
        "metadata_layer": 0,
        "metadata_date_field": "SRC_DATE",
        "photo_date": "",
    },
)

COUNTY_PROFILES: dict[str, CountyProfile] = {
    "denver": CountyProfile(
        key="denver",
        display_name="Denver",
        building_url=DENVER_BUILDINGS_URL,
        parcel_url=DENVER_PARCELS_URL,
        assessor_url=DENVER_ASSESSOR_URL,
        default_zip_codes="80121,80122",
        default_output_name="data/CO/Denver/parcels/denver_buildings_with_parcels.csv",
        default_parcel_cache_name="data/CO/Denver/parcels/colorado_parcel_data.csv",
        imagery_sources=DENVER_IMAGERY_SOURCES,
    ),
    "arapahoe": CountyProfile(
        key="arapahoe",
        display_name="Arapahoe County",
        building_url=ARAPAHOE_BUILDINGS_URL,
        parcel_url=ARAPAHOE_PARCELS_URL,
        assessor_url=None,
        default_zip_codes="",
        default_output_name="data/CO/Arapahoe/parcels/arapahoe_buildings_with_parcels.csv",
        default_parcel_cache_name="data/CO/Arapahoe/parcels/arapahoe_parcel_data.csv",
        imagery_sources=ARAPAHOE_IMAGERY_SOURCES,
    ),
    "jefferson": CountyProfile(
        key="jefferson",
        display_name="Jefferson County",
        building_url=JEFFERSON_BUILDINGS_URL,
        parcel_url=JEFFERSON_PARCELS_URL,
        assessor_url=None,
        default_zip_codes="",
        default_output_name="data/CO/Jefferson/parcels/jefferson_buildings_with_parcels.csv",
        default_parcel_cache_name="data/CO/Jefferson/parcels/jefferson_parcel_data.csv",
        imagery_sources=JEFFERSON_IMAGERY_SOURCES,
    ),
    "adams": CountyProfile(
        key="adams",
        display_name="Adams County",
        building_url=ADAMS_BUILDINGS_URL,
        parcel_url=ADAMS_PARCELS_URL,
        assessor_url=None,
        default_zip_codes="",
        default_output_name="data/CO/Adams/parcels/adams_buildings_with_parcels.csv",
        default_parcel_cache_name="data/CO/Adams/parcels/adams_parcel_data.csv",
        imagery_sources=ADAMS_IMAGERY_SOURCES,
    ),
}


def county_profile(key: str) -> CountyProfile:
    normalized = (key or "denver").strip().lower()
    try:
        return COUNTY_PROFILES[normalized]
    except KeyError as exc:
        supported = ", ".join(sorted(COUNTY_PROFILES))
        raise ValueError(f"Unsupported county profile '{key}'. Supported profiles: {supported}") from exc


def primary_imagery_source(profile: CountyProfile) -> dict:
    return profile.imagery_sources[0]
