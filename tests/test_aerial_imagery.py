import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image
from shapely.geometry import box

import collect_county_buildings_with_parcels as collector
from county_config import ADAMS_IMAGERY_SOURCES, DENVER_IMAGERY_SOURCES, JEFFERSON_IMAGERY_SOURCES
from generate_roof_intelligence_reports import aerial_photo_age_years


class AerialImageryTests(unittest.TestCase):
    def test_metadata_url_keeps_feature_layer_number(self):
        url = "https://example.test/arcgis/rest/services/Buildings/FeatureServer/7/query"
        self.assertEqual(
            collector.metadata_url(url),
            "https://example.test/arcgis/rest/services/Buildings/FeatureServer/7",
        )

    def test_crs_initialization_fails_closed_when_metadata_is_unavailable(self):
        original_building_crs = collector.BUILDING_CRS
        original_parcel_crs = collector.PARCEL_CRS
        try:
            with patch.object(collector, "inspect_service_metadata", return_value={}):
                with self.assertRaisesRegex(RuntimeError, "Unable to determine"):
                    collector.init_crs_transformers("buildings", "parcels")
        finally:
            collector.BUILDING_CRS = original_building_crs
            collector.PARCEL_CRS = original_parcel_crs

    def test_default_crop_buffer_is_40_feet(self):
        self.assertEqual(collector.AI_CROP_BUFFER_FEET, 40.0)

    def test_jefferson_prefers_official_drapp_with_esri_fallback(self):
        self.assertEqual(JEFFERSON_IMAGERY_SOURCES[0]["key"], "jeffco_drapp_2022")
        self.assertEqual(JEFFERSON_IMAGERY_SOURCES[0]["kind"], "ImageServer")
        self.assertEqual(JEFFERSON_IMAGERY_SOURCES[1]["key"], "world_imagery")

    def test_denver_uses_current_world_imagery_with_official_2022_archive_fallback(self):
        self.assertEqual(DENVER_IMAGERY_SOURCES[0]["key"], "world_imagery")
        self.assertEqual(DENVER_IMAGERY_SOURCES[1]["key"], "drapp_2022")
        self.assertEqual(DENVER_IMAGERY_SOURCES[1]["photo_date"], "2022")
        self.assertIn("Public_imagery", DENVER_IMAGERY_SOURCES[1]["index_url"])

    def test_esri_exports_are_limited_to_stable_size(self):
        self.assertEqual(ADAMS_IMAGERY_SOURCES[0]["min_export_pixels"], 640)
        self.assertEqual(ADAMS_IMAGERY_SOURCES[0]["max_export_pixels"], 640)
        self.assertEqual(JEFFERSON_IMAGERY_SOURCES[1]["min_export_pixels"], 640)
        self.assertEqual(JEFFERSON_IMAGERY_SOURCES[1]["max_export_pixels"], 640)

    def test_native_resolution_caps_jefferson_export(self):
        source = dict(JEFFERSON_IMAGERY_SOURCES[0])
        record = {"jeffco_drapp_2022_aerial_native_resolution": 0.1524003048}
        bounds = (0.0, 0.0, 155.5, 155.5)
        pixels = collector.native_capped_crop_pixels(record, source, bounds, 1536)
        self.assertEqual(pixels, 1021)

    def test_native_resolution_preserves_minimum_ai_input_size(self):
        source = dict(JEFFERSON_IMAGERY_SOURCES[0])
        record = {"jeffco_drapp_2022_aerial_native_resolution": 0.1524003048}
        bounds = (0.0, 0.0, 50.0, 50.0)
        pixels = collector.native_capped_crop_pixels(record, source, bounds, 1536)
        self.assertEqual(pixels, 640)

    def test_primary_source_falls_back_after_failed_preferred_source(self):
        original_sources = collector.IMAGERY_SOURCES
        try:
            collector.IMAGERY_SOURCES = list(JEFFERSON_IMAGERY_SOURCES)
            record = {
                "jeffco_drapp_2022_aerial_image_url": "https://example.test/preferred",
                "jeffco_drapp_2022_aerial_qa_status": "missing",
                "world_imagery_aerial_image_url": "https://example.test/fallback",
                "world_imagery_aerial_image_file": "/tmp/fallback.jpg",
                "world_imagery_aerial_qa_status": "ok",
            }
            collector.sync_primary_aerial_fields(record)
            self.assertEqual(record["primary_aerial_source"], "Esri World Imagery")
            self.assertEqual(record["primary_aerial_image_file"], "/tmp/fallback.jpg")
        finally:
            collector.IMAGERY_SOURCES = original_sources

    def test_cached_tiles_are_used_when_mapserver_export_is_empty(self):
        source = {
            "key": "world_imagery",
            "kind": "MapServer",
            "url": "https://example.test/MapServer",
            "crop_tile_service_url": "https://example.test/MapServer",
            "crop_tile_level": 19,
            "image_crs": 3857,
            "image_units": "meters",
            "min_export_pixels": 640,
            "max_export_pixels": 640,
        }
        polygon = box(-11688400, 4827560, -11688340, 4827620)
        with TemporaryDirectory() as directory, (
            patch.object(collector, "building_polygon_for_imagery_source", return_value=polygon)
        ), patch.object(
            collector, "urlopen", return_value=BytesIO(b'{"href": ""}')
        ), patch.object(
            collector, "fetch_image_tile", return_value=Image.new("RGB", (256, 256), "green")
        ):
            output = collector.save_ai_crop_image(
                {"parcel_number": "test-parcel"}, source, directory, 640, 40, "jpg"
            )

            self.assertTrue(Path(output).is_file())
            with Image.open(output) as image:
                self.assertEqual(max(image.size), 640)
            self.assertEqual(collector.image_qa(output)["status"], "blank")

    def test_year_only_imagery_date_is_used_conservatively(self):
        row = {"Primary Aerial Photo Date": "2022"}
        age = aerial_photo_age_years(row, as_of=date(2026, 7, 14))
        self.assertGreater(age, 3.5)
        self.assertLess(age, 3.6)


if __name__ == "__main__":
    unittest.main()
