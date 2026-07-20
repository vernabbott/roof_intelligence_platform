import unittest

import collect_county_buildings_with_parcels as collector
import collect_denver_buildings_with_parcels as legacy_collector
from county_config import COUNTY_PROFILES
from generate_roof_intelligence_reports import row_county_name


class CountyNeutralWorkflowTests(unittest.TestCase):
    def test_legacy_collector_name_is_only_an_alias(self):
        self.assertIs(legacy_collector, collector)

    def test_county_profiles_have_no_retired_zip_scope(self):
        for county, profile in COUNTY_PROFILES.items():
            self.assertFalse(hasattr(profile, "default_zip_codes"), county)

    def test_collector_has_no_zip_or_csv_entrypoint(self):
        self.assertFalse(hasattr(collector, "main"))
        self.assertFalse(hasattr(collector, "load_or_collect_parcels"))
        self.assertFalse(hasattr(collector, "write_parcel_cache"))

    def test_live_collector_requires_explicit_county_configuration(self):
        original_county = collector.ACTIVE_COUNTY_NAME
        original_source = collector.BUILDING_SOURCE_KIND
        try:
            collector.ACTIVE_COUNTY_NAME = ""
            collector.BUILDING_SOURCE_KIND = ""
            with self.assertRaisesRegex(RuntimeError, "explicit county profile"):
                collector.collect_buildings(1, "-105,39,-104,40")
            with self.assertRaisesRegex(RuntimeError, "explicit county profile"):
                collector.parcel_join_key({"PARID": "123"})
        finally:
            collector.ACTIVE_COUNTY_NAME = original_county
            collector.BUILDING_SOURCE_KIND = original_source

    def test_county_is_not_inferred_from_denver_city(self):
        self.assertEqual(row_county_name({"Building City": "Denver"}), "Unknown-County")
        self.assertEqual(row_county_name({"County": "Denver"}), "Denver")


if __name__ == "__main__":
    unittest.main()
