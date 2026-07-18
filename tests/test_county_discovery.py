import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

import building_footprint_store
import collect_denver_buildings_with_parcels as collector
from county_config import COUNTY_PROFILES


NEW_COUNTIES = {"boulder", "broomfield", "clear_creek", "douglas", "larimer", "weld"}
ORIGINAL_COUNTIES = {"denver", "adams", "arapahoe", "jefferson"}


class CountyDiscoveryProfileTests(unittest.TestCase):
    def test_six_counties_have_parcel_building_and_imagery_profiles(self):
        self.assertTrue(NEW_COUNTIES.issubset(COUNTY_PROFILES))
        for county in NEW_COUNTIES:
            profile = COUNTY_PROFILES[county]
            self.assertTrue(profile.parcel_url.endswith("/query"), county)
            self.assertEqual(profile.building_source, "postgis", county)
            self.assertEqual(profile.building_crs, 4326, county)
            self.assertTrue(profile.imagery_sources, county)

    def test_all_counties_use_bounded_postgis_primary_footprints(self):
        for county, profile in COUNTY_PROFILES.items():
            self.assertEqual(profile.building_source, "postgis", county)
            self.assertEqual(profile.building_crs, 4326, county)

    def test_original_counties_retain_county_footprints_as_secondary_sources(self):
        for county in ORIGINAL_COUNTIES:
            self.assertTrue(COUNTY_PROFILES[county].building_url.endswith("/query"), county)

    def test_larimer_uses_current_county_imagery(self):
        source = COUNTY_PROFILES["larimer"].imagery_sources[0]
        self.assertEqual(source["photo_date"], "2025")
        self.assertIn("larimer.org", source["url"])


class BuildingFootprintStoreTests(unittest.TestCase):
    def test_only_automatic_microsoft_canonical_records_are_revalidated(self):
        base = {
            "canonical_status": "validated",
            "source": building_footprint_store.MICROSOFT_SOURCE,
        }
        self.assertFalse(building_footprint_store.canonical_needs_revalidation(base))
        self.assertTrue(
            building_footprint_store.canonical_needs_revalidation(
                {**base, "canonical_revalidation_due": True}
            )
        )
        self.assertFalse(
            building_footprint_store.canonical_needs_revalidation(
                {**base, "canonical_status": "manually_resolved", "canonical_sources_changed": True}
            )
        )

    def test_parse_envelope_rejects_unbounded_or_reversed_input(self):
        with self.assertRaisesRegex(ValueError, "four-number"):
            building_footprint_store.parse_envelope("1,2,3")
        with self.assertRaisesRegex(ValueError, "invalid"):
            building_footprint_store.parse_envelope("3,2,1,4")

    def test_postgis_query_is_county_and_envelope_bounded(self):
        row = {
            "id": 7,
            "external_id": "abc",
            "source": "Microsoft US Building Footprints",
            "footprint_sqft": 1200,
            "perimeter_ft": 150,
            "building_geometry": "POLYGON ((-105 40, -104 40, -104 41, -105 41, -105 40))",
        }
        mappings = MagicMock()
        mappings.__iter__.return_value = iter([row])
        execution = MagicMock()
        execution.mappings.return_value = mappings
        connection = MagicMock()
        connection.execute.return_value = execution
        context = MagicMock()
        context.__enter__.return_value = connection
        fake_engine = MagicMock()
        fake_engine.connect.return_value = context

        with (
            patch.object(building_footprint_store, "engine", return_value=fake_engine),
            patch.object(building_footprint_store, "canonical_schema_available", return_value=False),
        ):
            records = building_footprint_store.collect_buildings_in_envelope(
                "Boulder County", "-105,40,-104,41", limit=25
            )

        params = connection.execute.call_args.args[1]
        self.assertEqual(params["county"], "Boulder")
        self.assertEqual(params["source"], building_footprint_store.MICROSOFT_SOURCE)
        self.assertEqual(params["row_limit"], 25)
        self.assertEqual(records[0]["OBJECTID"], 7)
        self.assertEqual(records[0]["building_shape_area"], 1200)

    def test_canonical_schema_references_selected_raw_geometry(self):
        migration = (
            Path(__file__).resolve().parents[1]
            / "docs/ai/supabase/canonical_building_footprints.sql"
        ).read_text(encoding="utf-8")

        canonical_definition = migration.split("CREATE TABLE IF NOT EXISTS canonical_building_footprints", 1)[1].split(");", 1)[0]
        self.assertIn("selected_source_footprint_id", canonical_definition)
        self.assertNotIn("geometry(MultiPolygon", canonical_definition)


class CrossCountyGeometryTests(unittest.TestCase):
    def test_denver_schedule_number_precedes_short_parcel_fragment(self):
        original_county = collector.ACTIVE_COUNTY_NAME
        try:
            collector.ACTIVE_COUNTY_NAME = "Denver"
            value = collector.parcel_join_key(
                {"SCHEDNUM": "0508500065000", "PARCELNUM": "065"}
            )
        finally:
            collector.ACTIVE_COUNTY_NAME = original_county

        self.assertEqual(value, "0508500065000")

    def test_county_footprint_within_tolerance_validates(self):
        primary = {
            "building_geometry": "POLYGON ((-105 40, -104.9999 40, -104.9999 40.0001, -105 40.0001, -105 40))",
            "footprint_sqft": 10100,
        }
        secondary = [{**primary, "footprint_sqft": 10000}]

        result = collector.validate_building_footprint_sources(primary, secondary)

        self.assertEqual(result["status"], "validated")
        self.assertLess(result["difference_pct"], 5)

    def test_county_footprint_over_tolerance_is_discrepancy(self):
        geometry = "POLYGON ((-105 40, -104.9999 40, -104.9999 40.0001, -105 40.0001, -105 40))"
        result = collector.validate_building_footprint_sources(
            {"building_geometry": geometry, "footprint_sqft": 10000},
            [{"building_geometry": geometry, "footprint_sqft": 12000}],
        )

        self.assertEqual(result["status"], "discrepancy")
        self.assertEqual(result["difference_pct"], 20)

    def test_world_imagery_bounds_do_not_exceed_finest_cached_scale(self):
        source = COUNTY_PROFILES["boulder"].imagery_sources[0]
        bounds = collector.enforce_minimum_export_resolution((0, 0, 20, 30), source)

        self.assertGreaterEqual(bounds[2] - bounds[0], 192)
        self.assertEqual(bounds[2] - bounds[0], bounds[3] - bounds[1])

    def test_larimer_parcel_number_precedes_schedule_number(self):
        original_county = collector.ACTIVE_COUNTY_NAME
        try:
            collector.ACTIVE_COUNTY_NAME = "Larimer"
            value = collector.parcel_join_key(
                {"PARCELNUM": "9712307005", "SCHEDNUM": "0043737"}
            )
        finally:
            collector.ACTIVE_COUNTY_NAME = original_county
        self.assertEqual(value, "9712307005")

    def test_imported_footprint_area_is_not_recomputed_in_parcel_units(self):
        building = {
            "building_geometry": "POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))",
            "footprint_sqft": 44569.53,
        }
        parcel = {
            "PIN": "test-parcel",
            "parcel_geometry": "POLYGON ((-1 -1, 2 -1, 2 2, -1 2, -1 -1))",
        }
        original_to_parcel = collector.TRANSFORMER_TO_PARCEL
        try:
            collector.TRANSFORMER_TO_PARCEL = None
            records = collector.combine_data([building], [parcel])
        finally:
            collector.TRANSFORMER_TO_PARCEL = original_to_parcel

        self.assertEqual(records[0]["building_footprint_sqft"], 44570)
        self.assertEqual(records[0]["parcel_number"], "TESTPARCEL")


if __name__ == "__main__":
    unittest.main()
