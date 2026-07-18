# Aerial Imagery Source and Crop Validation

**Validation date:** July 14, 2026
**Status:** Implemented for future collections and refreshed for the seven roof-reference pilot buildings

## Implemented behavior

- The default building-footprint buffer for AI crops is 40 feet instead of 100 feet.
- Denver now uses date-aware Esri World Imagery for report crops instead of the 2018 DRAPP archive. The official [DRCOG public imagery catalog](https://services3.arcgis.com/DgjqnJA1rgO92Soi/arcgis/rest/services/Public_imagery/FeatureServer/57) provides the 2022 original GeoTIFF as a fallback when original-tile retrieval is requested.
- Jefferson County uses the official [Jefferson County DRAPP 2022 ImageServer](https://gisportal.jeffco.us/image/rest/services/DRAPP/DRAPP2022/ImageServer) as its primary aerial source.
- Jefferson County retains Esri World Imagery as an automatic fallback when the preferred image is missing, blank, unreadable, or fails to download.
- Adams County continues to use Esri World Imagery because no equivalent public, official Adams County high-resolution ImageServer was identified during this review.
- Arapahoe County continues to use its official 2024 ImageServer after live export validation.
- Export dimensions are capped by the source's native ground resolution. The pipeline does not request extra pixels when they would only enlarge the same source detail.
- The selected source, project/capture date, native resolution, exported dimensions, and image QA results are written to the building CSV.

## Resolution findings

The Esri source catalog reports `0.34 meters/pixel` at the seven pilot locations. A 1024-pixel Esri export therefore did not provide 1024 pixels of independent roof detail; depending on crop size, it was interpolated or could return blank below the locally available cache scale. Esri exports are now standardized at 640×640. This preserves stable vision-model input dimensions without claiming that interpolation creates new source detail.

The Jefferson County DRAPP 2022 service reports `0.1524003048 meters/pixel`, approximately six inches per pixel. This provides more than twice the linear source detail available from Esri at the Jefferson pilot locations. The refreshed Jefferson crops are 1024×1024, 1024×1024, and 1021×1021 based on each building's crop extent and native resolution.

DRCOG states that its regional program acquires high-resolution aerial imagery every two years. Its public catalog currently highlights 2022 imagery, while more current imagery is distributed through its acquisition partners rather than as a generally available public county service. See the [DRCOG data acquisition program](https://www.drcog.org/data-maps-modeling/data-acquisition-projects) and [DRCOG Regional Data Catalog](https://data.drcog.org/).

## Pilot comparison images

These images compare the previous pilot input on the left with the refreshed input on the right. No AI classification calls were made during this imagery refresh.

- [4201 E 72nd Ave](../../pilot_outputs_v1_1/imagery_validation/0172131300018-4201-e-72nd-ave-comparison.jpg)
- [7200 Quebec Pkwy](../../pilot_outputs_v1_1/imagery_validation/0172133301001-7200-quebec-pkwy-comparison.jpg)
- [5101 Quebec St](../../pilot_outputs_v1_1/imagery_validation/0182317107020-5101-quebec-st-comparison.jpg)
- [6345 Colorado Blvd](../../pilot_outputs_v1_1/imagery_validation/0182512101037-6345-colorado-blvd-comparison.jpg)
- [12043 W Alameda Pkwy](../../pilot_outputs_v1_1/imagery_validation/4917105011-12043-w-alameda-pkwy-comparison.jpg)
- [12364 W Alameda Pkwy](../../pilot_outputs_v1_1/imagery_validation/4917406019-12364-w-alameda-pkwy-comparison.jpg)
- [12250 W Kentucky Dr](../../pilot_outputs_v1_1/imagery_validation/4917423001-12250-w-kentucky-dr-comparison.jpg)

## Operational note

The Jefferson source is older than the current Esri capture but materially sharper. Reports preserve the honest year-only value `2022`, and the report-age adjustment treats it conservatively as the end of that year. The source decision should be reviewed periodically because public imagery services and licensing can change.

World Imagery exports are expanded to at least the service's finest cached resolution before requesting pixels. This prevents small-building requests from asking for a scale the cached service cannot provide, which previously returned HTTP 500 for some sites.
