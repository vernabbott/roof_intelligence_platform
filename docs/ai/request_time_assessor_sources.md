# Request-Time Assessor Sources

**Configured:** July 17, 2026
**Scope:** All ten configured Colorado counties

The report workflow must query these sources only for parcel or account identifiers associated with a user-selected address or map area. It must not perform an unbounded county-wide assessor scan.

| County | Official request-time source | Building characteristics |
| --- | --- | --- |
| Denver | Apartment and Commercial Characteristics table | Year built, use, gross/net area, floors and valuation; gross/net areas are not treated as footprints |
| Adams | Parcels, Property Improvements, and Property Values ArcGIS services | Year built, area, property type, exterior and valuation |
| Arapahoe | County parcels plus the official 2025 commercial assessment-transparency layer | Commercial square footage, use/classification and valuation; no published building year |
| Boulder | Parcel Accounts and BoCo Building Info ArcGIS services | Year built, building areas, design/class and bathroom counts |
| Broomfield | Combined assessor parcel ArcGIS service | Year built, use, area, stories, roof cover and valuation |
| Clear Creek | Assessor Owner and Assessor Residential ArcGIS tables | Residential year/area; official TaxWeb is retained as the commercial-detail fallback |
| Douglas | Official assessor account-query service | Detailed nested building, use, age, area, construction, roof and valuation data |
| Jefferson | Combined Parcel and assessor-detail ArcGIS service | Year built, use, gross area, floors, construction and valuation |
| Larimer | Official Assessor JSON API | Property/account search followed by detail, improvement and value-detail calls |
| Weld | Current Account Inventory, Improvements and Ownership ArcGIS tables | Year built, use, area, stories, roof, construction, ownership and value data |

## Implementation

- Source definitions are in `county_config.py` under `ASSESSOR_SOURCES`.
- `assessor_detail.py` performs bounded request-time lookups and follows parcel-to-account relationships when a county separates its tables.
- `pcs_request_workflow.py` validates the PCS selection envelope, restricts work to its parcel IDs, and fills blank canonical report fields from assessor records.
- `generate_roof_intelligence_reports.py --pcs-request <request.json>` filters the input to the PCS selection, runs the assessor lookups, and records source counts, detail links, and warnings in the report manifest.
- A request is limited to 100 parcel identifiers.
- Every returned raw record is tagged with its source key and role for traceability.
- Clear Creek TaxWeb links are returned as fallbacks; HTML parsing is intentionally not treated as a stable structured API.

## PCS request contract

PCS must resolve its address or map selection to parcel identifiers before it starts the report job. An address request contains exactly one property. A map request can contain up to 100 properties and may span supported counties.

```json
{
  "request_id": "PCS-2026-00042",
  "selection_type": "address",
  "properties": [
    {
      "county": "Boulder",
      "parcel_id": "146330324001",
      "address": "1325 Pearl St, Boulder, CO"
    }
  ]
}
```

Map selection example:

```json
{
  "request_id": "PCS-2026-00043",
  "selection_type": "map",
  "properties": [
    {"county": "Adams", "parcel_id": "0172131300018", "address": "4201 E 72nd Ave"},
    {"county": "Jefferson", "parcel_id": "4917406019", "address": "12364 W Alameda Pkwy"}
  ]
}
```

The report input CSV can contain a larger working set, but only rows matching both the county and parcel IDs in this envelope are eligible. Generation fails before creating reports if any requested parcel is missing from the input.

```bash
./.venv/bin/python generate_roof_intelligence_reports.py \
  --input /path/to/pcs-selected-properties.csv \
  --pcs-request /path/to/pcs-request.json \
  --manifest /path/to/report-manifest.json \
  --output-dir /path/to/output
```

The manifest includes the PCS request ID and selection type. Each generated record includes an `assessor` object containing record counts by source, fallback links, and user-facing warnings. Existing nonblank CSV values are preserved; assessor data only fills missing canonical fields such as year built, use, stories, construction type, and land value.

## PCS Proposal Management integration

The adjacent PCS application is connected directly as well:

- `roof_intelligence_single_address.py` runs the configured assessor lookup after the address resolves to a parcel and before AI analysis/report rendering.
- A map candidate's known parcel ID is passed to the address worker as `--parcel-id`. The worker stops if address resolution returns a different parcel.
- Assessor source counts, fallback links, and warnings are returned with the completed PCS result and retained in the job/report JSON.
- Partial assessor results and single-source footprint warnings create a **Property data notice** in the existing PCS Notifications panel.
- The standalone script's default project path points to this PilotPoint IQ project.

## Parcel, building, and imagery discovery

PCS can now discover report candidates for all ten configured counties. Discovery remains bounded to the single geocoded address point or the user-selected map geometry.

| County | Parcel discovery | Building discovery | Primary imagery |
| --- | --- | --- | --- |
| Denver | Denver property parcels | Supabase primary; Denver outlines secondary | Esri World Imagery; DRCOG 2022 original-tile fallback |
| Adams | County Parcels | Supabase primary; county footprints secondary | Esri World Imagery |
| Arapahoe | County Parcels | Supabase primary; county footprints secondary | Arapahoe County 2024 aerials |
| Jefferson | County Parcels | Supabase primary; county roofprints secondary | Jefferson County DRAPP 2022 |
| Boulder | County Parcel Accounts | Supabase `building_footprints` | Esri World Imagery |
| Broomfield | County Parcels | Supabase `building_footprints` | Esri World Imagery |
| Clear Creek | County Property parcels; address point resolved by geocoding | Supabase `building_footprints` | Esri World Imagery |
| Douglas | County POSSE parcels; address point resolved by geocoding | Supabase `building_footprints` | Esri World Imagery |
| Larimer | County Parcels | Supabase `building_footprints` | Larimer County 2025 imagery |
| Weld | County open-data Parcels | Supabase `building_footprints` | Esri World Imagery |

The imported building-footprint area is retained as square feet instead of being recalculated in a county parcel layer's native units. For an individual-address request on a parcel with several structures, the building containing or nearest the geocoded address point is selected. Map discovery reverse-geocodes parcel centroids only when the parcel service does not publish a usable situs address.

For Denver, Adams, Arapahoe and Jefferson, the selected Supabase footprint is compared with the overlapping county footprint. A difference of more than 5% stops report creation and returns a discrepancy error. If only one footprint source contains the selected structure, report creation continues with an informational user notice. Assessor data participates in the same 5% blocking comparison only when the county explicitly labels a value as building footprint or ground-floor area. Gross, total, finished and living areas are intentionally excluded because they are not roof-footprint measurements.

## Scheduled health check

`county_discovery_health.py` runs a bounded live address through parcel, Supabase footprint, county secondary footprint where configured, assessor and imagery discovery for each county. It writes machine-readable JSON and returns a nonzero status for unavailable services. `--strict-discrepancies` also fails when the two geometry sources differ by more than 5%.

```bash
./.venv/bin/python county_discovery_health.py \
  --strict-discrepancies \
  --output data/health/county-discovery-latest.json
```

The project includes `scripts/com.pilotpoint.county-discovery-health.plist`, a macOS LaunchAgent definition configured for 6:00 AM daily execution.

## Known limitations

- Arapahoe County's published commercial layer does not include year built.
- Clear Creek publishes structured building characteristics for residential accounts, but not an equivalent commercial table. Commercial detail requires the official TaxWeb record unless the county publishes another structured service.
- County schemas and endpoints can change. The scheduled health monitor reports availability and schema/identifier failures but does not silently change source mappings.
- Esri World Imagery is used where a county did not expose a current, public, token-free imagery export service. Imagery dates and resolution still come from the configured imagery metadata layer when available.
