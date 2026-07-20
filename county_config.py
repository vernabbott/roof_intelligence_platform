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
    imagery_sources: tuple[dict, ...]
    building_source: str = "arcgis"
    building_crs: int | None = None
    parcel_id_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssessorSource:
    """One request-time assessor source used to enrich a selected parcel.

    ``lookup_by`` describes the identifier expected by the source. Sources
    that use an account number are queried after a parcel/account source has
    returned that account number.
    """

    key: str
    label: str
    kind: str
    url: str
    role: str
    lookup_by: str
    lookup_field: str = ""
    alternate_lookup_fields: tuple[str, ...] = ()
    identifier_groupings: tuple[tuple[int, ...], ...] = ()
    parcel_fields: tuple[str, ...] = ()
    account_fields: tuple[str, ...] = ()
    notes: str = ""


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

BOULDER_PARCELS_URL = (
    "https://services3.arcgis.com/0jWpHMuhmHsukKE3/arcgis/rest/services/"
    "ParcelAccounts/FeatureServer/5/query"
)

BROOMFIELD_PARCELS_URL = (
    "https://services1.arcgis.com/vXSRPZbyyOmH9pek/ArcGIS/rest/services/"
    "Parcels/FeatureServer/0/query"
)

CLEAR_CREEK_PARCELS_URL = (
    "https://services1.arcgis.com/faTiISwEuJk1lvB1/ArcGIS/rest/services/"
    "Property/FeatureServer/12/query"
)

DOUGLAS_PARCELS_URL = (
    "https://apps.douglas.co.us/gisod/rest/services/"
    "POSSE_Parcels/FeatureServer/0/query"
)

LARIMER_PARCELS_URL = (
    "https://maps1.larimer.org/arcgis/rest/services/"
    "MapServices/Parcels/MapServer/3/query"
)

WELD_PARCELS_URL = (
    "https://services.arcgis.com/ewjSqmSyHJnkfBLL/arcgis/rest/services/"
    "Parcels_open_data/FeatureServer/0/query"
)

DENVER_IMAGERY_SOURCES = (
    {
        "key": "world_imagery",
        "name": "Esri World Imagery MapServer",
        "label": "Esri World Imagery",
        "kind": "MapServer",
        "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer",
        "image_crs": 3857,
        "image_units": "meters",
        "minimum_export_resolution": 0.3,
        "min_export_pixels": 640,
        "max_export_pixels": 1024,
        "metadata_layer": 0,
        "metadata_date_field": "SRC_DATE",
        "metadata_resolution_field": "SRC_RES",
        "photo_date": "",
    },
    {
        "key": "drapp_2022",
        "name": "DRCOG DRAPP 2022 original tile",
        "label": "DRCOG DRAPP 2022",
        "kind": "DRAPPOriginalTile",
        "index_url": "https://services3.arcgis.com/DgjqnJA1rgO92Soi/arcgis/rest/services/Public_imagery/FeatureServer/57",
        "index_crs": 3857,
        "url_field": "path",
        "photo_date": "2022",
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
        "key": "jeffco_drapp_2022",
        "name": "Jefferson County DRAPP 2022 ImageServer",
        "label": "Jefferson County DRAPP 2022",
        "kind": "ImageServer",
        "url": "https://gisportal.jeffco.us/image/rest/services/DRAPP/DRAPP2022/ImageServer",
        "image_crs": 3857,
        "image_units": "meters",
        # Official ImageServer metadata reports 0.1524003048 meters (6 inches)
        # per native source pixel. Exports are capped at native detail below.
        "native_resolution": 0.15240030480060823,
        "min_export_pixels": 640,
        "max_export_pixels": 1024,
        # The service identifies the acquisition by project year rather than an
        # exact capture date, so preserve the honest year-only value.
        "photo_date": "2022",
    },
    {
        "key": "world_imagery",
        "name": "Esri World Imagery MapServer",
        "label": "Esri World Imagery",
        "kind": "MapServer",
        "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer",
        "image_crs": 3857,
        "image_units": "meters",
        "minimum_export_resolution": 0.3,
        # At the current pilot sites, 1024-pixel exports add interpolation and
        # can return blank below the locally available cache scale.
        "min_export_pixels": 640,
        "max_export_pixels": 640,
        "metadata_layer": 0,
        "metadata_date_field": "SRC_DATE",
        "metadata_resolution_field": "SRC_RES",
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
        "minimum_export_resolution": 0.3,
        "min_export_pixels": 640,
        "max_export_pixels": 640,
        "metadata_layer": 0,
        "metadata_date_field": "SRC_DATE",
        "metadata_resolution_field": "SRC_RES",
        "photo_date": "",
    },
)

WORLD_IMAGERY_SOURCES = (
    {
        "key": "world_imagery",
        "name": "Esri World Imagery MapServer",
        "label": "Esri World Imagery",
        "kind": "MapServer",
        "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer",
        "image_crs": 3857,
        "image_units": "meters",
        "minimum_export_resolution": 0.3,
        "min_export_pixels": 640,
        "max_export_pixels": 1024,
        "metadata_layer": 0,
        "metadata_date_field": "SRC_DATE",
        "metadata_resolution_field": "SRC_RES",
        "photo_date": "",
    },
)

LARIMER_IMAGERY_SOURCES = (
    {
        "key": "larimer_2025",
        "name": "Larimer County 2025 Aerial Imagery",
        "label": "Larimer County 2025 Aerials",
        "kind": "MapServer",
        "url": "https://maps1.larimer.org/arcgis/rest/services/Imagery/imagery2025FullCounty/MapServer",
        "image_crs": 2876,
        "image_units": "feet",
        "photo_date": "2025",
        "min_export_pixels": 640,
        "max_export_pixels": 1024,
    },
)


# Official public assessor sources used for request-time parcel enrichment.
# These are deliberately parcel/account scoped; callers must not replace the
# configured lookup with an unbounded ``1=1`` collection.
ASSESSOR_SOURCES: dict[str, tuple[AssessorSource, ...]] = {
    "denver": (
        AssessorSource(
            key="denver_commercial_characteristics",
            label="Denver Apartment and Commercial Characteristics",
            kind="arcgis",
            url=DENVER_ASSESSOR_URL,
            role="building",
            lookup_by="parcel",
            lookup_field="PARID",
            parcel_fields=("PARID",),
            notes="Gross, net, basement and total areas are not treated as roof-footprint area.",
        ),
    ),
    "adams": (
        AssessorSource(
            key="adams_parcel",
            label="Adams County Parcels",
            kind="arcgis",
            url="https://services3.arcgis.com/4PNQOtAivErR7nbT/arcgis/rest/services/Parcels/FeatureServer/0/query",
            role="parcel_account",
            lookup_by="parcel",
            lookup_field="PIN",
            alternate_lookup_fields=("PARCELNB",),
            parcel_fields=("PIN", "PARCELNB"),
            account_fields=(),
        ),
        AssessorSource(
            key="adams_improvements",
            label="Adams County Property Improvements",
            kind="arcgis",
            url="https://services3.arcgis.com/4PNQOtAivErR7nbT/arcgis/rest/services/Property_Improvements/FeatureServer/0/query",
            role="building",
            lookup_by="parcel",
            lookup_field="parcelnb",
            alternate_lookup_fields=("pin",),
            parcel_fields=("parcelnb", "pin"),
            account_fields=("accountno",),
        ),
        AssessorSource(
            key="adams_values",
            label="Adams County Property Values",
            kind="arcgis",
            url="https://services3.arcgis.com/4PNQOtAivErR7nbT/arcgis/rest/services/Property_Values/FeatureServer/0/query",
            role="valuation",
            lookup_by="parcel",
            lookup_field="parcelnb",
            alternate_lookup_fields=("pin",),
            parcel_fields=("parcelnb", "pin"),
            account_fields=("accountno",),
        ),
    ),
    "arapahoe": (
        AssessorSource(
            key="arapahoe_parcel",
            label="Arapahoe County Parcels",
            kind="arcgis",
            url="https://gis.arapahoegov.com/arcgis/rest/services/CountyFeatureService/FeatureServer/14/query",
            role="parcel_account",
            lookup_by="parcel",
            lookup_field="PARCEL_ID",
            alternate_lookup_fields=("PIN", "Folio"),
            identifier_groupings=((4, 2, 1, 2, 3),),
            parcel_fields=("PARCEL_ID", "PIN", "Folio"),
            account_fields=(),
        ),
        AssessorSource(
            key="arapahoe_commercial_values",
            label="Arapahoe County Commercial Parcel Values 2025",
            kind="arcgis",
            url="https://services2.arcgis.com/OSbOBWdLkmvu5I9F/arcgis/rest/services/Commercial_Parcel_Value_Change_2025/FeatureServer/0/query",
            role="commercial_assessment",
            lookup_by="parcel",
            lookup_field="PARCEL_ID",
            alternate_lookup_fields=("PIN", "Folio", "AIN"),
            identifier_groupings=((4, 2, 1, 2, 3),),
            parcel_fields=("PARCEL_ID", "PIN", "Folio", "AIN"),
            account_fields=("AIN",),
            notes="Official 2025 assessment-transparency layer; building year is not published in this service.",
        ),
    ),
    "boulder": (
        AssessorSource(
            key="boulder_parcel_accounts",
            label="Boulder County Parcel Accounts",
            kind="arcgis",
            url="https://services3.arcgis.com/0jWpHMuhmHsukKE3/arcgis/rest/services/ParcelAccounts/FeatureServer/5/query",
            role="parcel_account",
            lookup_by="parcel",
            lookup_field="ParcelNo",
            parcel_fields=("ParcelNo",),
            account_fields=("AccountNo",),
        ),
        AssessorSource(
            key="boulder_building_info",
            label="Boulder County Building Info",
            kind="arcgis",
            url="https://services3.arcgis.com/0jWpHMuhmHsukKE3/arcgis/rest/services/BoCoBuildingInfo/FeatureServer/0/query",
            role="building",
            lookup_by="account",
            lookup_field="AccountNo",
            account_fields=("AccountNo",),
        ),
    ),
    "broomfield": (
        AssessorSource(
            key="broomfield_parcels",
            label="City and County of Broomfield Parcels",
            kind="arcgis",
            url="https://services1.arcgis.com/vXSRPZbyyOmH9pek/ArcGIS/rest/services/Parcels/FeatureServer/0/query",
            role="combined",
            lookup_by="parcel",
            lookup_field="PARCELNUMBER",
            parcel_fields=("PARCELNUMBER",),
            account_fields=("ACCOUNTNUMBER",),
        ),
    ),
    "clear_creek": (
        AssessorSource(
            key="clear_creek_owner",
            label="Clear Creek County Assessor Owner Table",
            kind="arcgis",
            url="https://services1.arcgis.com/faTiISwEuJk1lvB1/ArcGIS/rest/services/Property/FeatureServer/27/query",
            role="parcel_account",
            lookup_by="parcel",
            lookup_field="PARCELNUMBER",
            parcel_fields=("PARCELNUMBER",),
            account_fields=("ACCOUNTNUMBER",),
        ),
        AssessorSource(
            key="clear_creek_residential",
            label="Clear Creek County Assessor Residential",
            kind="arcgis",
            url="https://services1.arcgis.com/faTiISwEuJk1lvB1/ArcGIS/rest/services/Property/FeatureServer/32/query",
            role="building",
            lookup_by="account",
            lookup_field="ACCOUNTNUMBER",
            account_fields=("ACCOUNTNUMBER",),
            notes="Residential characteristics only; commercial detail may require the official TaxWeb record.",
        ),
        AssessorSource(
            key="clear_creek_taxweb",
            label="Clear Creek County Assessor TaxWeb",
            kind="html_detail",
            url="https://assessor.co.clear-creek.co.us/assessor/taxweb/account.jsp?accountNum={account}",
            role="detail_fallback",
            lookup_by="account",
            account_fields=("ACCOUNTNUMBER",),
            notes="Official account-detail fallback for property classes not published in the ArcGIS residential table.",
        ),
    ),
    "douglas": (
        AssessorSource(
            key="douglas_account_query",
            label="Douglas County Assessor Account Query",
            kind="elasticsearch_proxy",
            url="https://apps.douglas.co.us/assessor/account-query",
            role="combined",
            lookup_by="parcel",
            lookup_field="state_parcel_number",
            parcel_fields=("state_parcel_number",),
            account_fields=("account_number",),
            notes="Official read-only assessor search endpoint; requests are POSTed as exact parcel/account term queries.",
        ),
    ),
    "jefferson": (
        AssessorSource(
            key="jefferson_parcel",
            label="Jefferson County Parcel and Assessor Detail",
            kind="arcgis",
            url="https://gisportal.jeffco.us/server2/rest/services/Parcel/FeatureServer/20/query",
            role="combined",
            lookup_by="parcel",
            lookup_field="PARCELID",
            alternate_lookup_fields=("PIN", "SPN", "AIN", "SCH"),
            identifier_groupings=((2, 3, 2, 3),),
            parcel_fields=("PARCELID", "PIN", "SPN", "AIN", "SCH"),
            account_fields=("SCH", "AIN"),
        ),
    ),
    "larimer": (
        AssessorSource(
            key="larimer_property_search",
            label="Larimer County Assessor Property Search",
            kind="larimer_json",
            url="https://apps.larimer.org/api/assessor2/property/",
            role="parcel_account",
            lookup_by="parcel",
            lookup_field="parcel",
            parcel_fields=("parcelnb",),
            account_fields=("accountno", "schedulenum"),
        ),
        AssessorSource(
            key="larimer_account_detail",
            label="Larimer County Assessor Account Detail",
            kind="larimer_json",
            url="https://apps.larimer.org/api/assessor2/",
            role="combined",
            lookup_by="account",
            lookup_field="accountno",
            parcel_fields=("parcelnb",),
            account_fields=("accountno",),
            notes="Query the detail and improvement resources for each exact account returned by property search.",
        ),
    ),
    "weld": (
        AssessorSource(
            key="weld_accounts",
            label="Weld County Assessor Current Account Inventory",
            kind="arcgis",
            url="https://services.arcgis.com/ewjSqmSyHJnkfBLL/arcgis/rest/services/AcctCurrentInvntry/FeatureServer/12/query",
            role="parcel_account",
            lookup_by="parcel",
            lookup_field="PARCELNO",
            parcel_fields=("PARCELNO",),
            account_fields=("ACCOUNTNO",),
        ),
        AssessorSource(
            key="weld_improvements",
            label="Weld County Assessor Improvements Current Inventory",
            kind="arcgis",
            url="https://services.arcgis.com/ewjSqmSyHJnkfBLL/arcgis/rest/services/Imps_CurrentInvntry/FeatureServer/14/query",
            role="building",
            lookup_by="account",
            lookup_field="ACCOUNTNO",
            account_fields=("ACCOUNTNO",),
        ),
        AssessorSource(
            key="weld_ownership",
            label="Weld County Assessor Ownership",
            kind="arcgis",
            url="https://services.arcgis.com/ewjSqmSyHJnkfBLL/arcgis/rest/services/Ownership2/FeatureServer/17/query",
            role="ownership",
            lookup_by="account",
            lookup_field="ACCOUNTNO",
            parcel_fields=("PARCELNB",),
            account_fields=("ACCOUNTNO",),
        ),
    ),
}

COUNTY_PROFILES: dict[str, CountyProfile] = {
    "denver": CountyProfile(
        key="denver",
        display_name="Denver",
        building_url=DENVER_BUILDINGS_URL,
        parcel_url=DENVER_PARCELS_URL,
        imagery_sources=DENVER_IMAGERY_SOURCES,
        building_source="postgis",
        building_crs=4326,
        parcel_id_fields=("SCHEDNUM", "PARID"),
    ),
    "arapahoe": CountyProfile(
        key="arapahoe",
        display_name="Arapahoe County",
        building_url=ARAPAHOE_BUILDINGS_URL,
        parcel_url=ARAPAHOE_PARCELS_URL,
        imagery_sources=ARAPAHOE_IMAGERY_SOURCES,
        building_source="postgis",
        building_crs=4326,
    ),
    "jefferson": CountyProfile(
        key="jefferson",
        display_name="Jefferson County",
        building_url=JEFFERSON_BUILDINGS_URL,
        parcel_url=JEFFERSON_PARCELS_URL,
        imagery_sources=JEFFERSON_IMAGERY_SOURCES,
        building_source="postgis",
        building_crs=4326,
    ),
    "adams": CountyProfile(
        key="adams",
        display_name="Adams County",
        building_url=ADAMS_BUILDINGS_URL,
        parcel_url=ADAMS_PARCELS_URL,
        imagery_sources=ADAMS_IMAGERY_SOURCES,
        building_source="postgis",
        building_crs=4326,
    ),
    "boulder": CountyProfile(
        key="boulder",
        display_name="Boulder County",
        building_url="",
        parcel_url=BOULDER_PARCELS_URL,
        imagery_sources=WORLD_IMAGERY_SOURCES,
        building_source="postgis",
        building_crs=4326,
    ),
    "broomfield": CountyProfile(
        key="broomfield",
        display_name="Broomfield County",
        building_url="",
        parcel_url=BROOMFIELD_PARCELS_URL,
        imagery_sources=WORLD_IMAGERY_SOURCES,
        building_source="postgis",
        building_crs=4326,
    ),
    "clear_creek": CountyProfile(
        key="clear_creek",
        display_name="Clear Creek County",
        building_url="",
        parcel_url=CLEAR_CREEK_PARCELS_URL,
        imagery_sources=WORLD_IMAGERY_SOURCES,
        building_source="postgis",
        building_crs=4326,
    ),
    "douglas": CountyProfile(
        key="douglas",
        display_name="Douglas County",
        building_url="",
        parcel_url=DOUGLAS_PARCELS_URL,
        imagery_sources=WORLD_IMAGERY_SOURCES,
        building_source="postgis",
        building_crs=4326,
    ),
    "larimer": CountyProfile(
        key="larimer",
        display_name="Larimer County",
        building_url="",
        parcel_url=LARIMER_PARCELS_URL,
        imagery_sources=LARIMER_IMAGERY_SOURCES,
        building_source="postgis",
        building_crs=4326,
    ),
    "weld": CountyProfile(
        key="weld",
        display_name="Weld County",
        building_url="",
        parcel_url=WELD_PARCELS_URL,
        imagery_sources=WORLD_IMAGERY_SOURCES,
        building_source="postgis",
        building_crs=4326,
    ),
}


def county_profile(key: str) -> CountyProfile:
    normalized = (key or "").strip().lower()
    try:
        return COUNTY_PROFILES[normalized]
    except KeyError as exc:
        supported = ", ".join(sorted(COUNTY_PROFILES))
        raise ValueError(f"Unsupported county profile '{key}'. Supported profiles: {supported}") from exc


def primary_imagery_source(profile: CountyProfile) -> dict:
    return profile.imagery_sources[0]


def assessor_sources(county_key: str) -> tuple[AssessorSource, ...]:
    """Return request-time assessor sources for a supported county key."""
    normalized = (county_key or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "clearcreek": "clear_creek",
        "clear_creek_county": "clear_creek",
        "broomfield_county": "broomfield",
    }
    normalized = aliases.get(normalized, normalized.removesuffix("_county"))
    try:
        return ASSESSOR_SOURCES[normalized]
    except KeyError as exc:
        supported = ", ".join(sorted(ASSESSOR_SOURCES))
        raise ValueError(
            f"Unsupported assessor county '{county_key}'. Supported counties: {supported}"
        ) from exc
