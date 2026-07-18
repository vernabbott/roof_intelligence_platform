import unittest
from unittest.mock import patch

import collect_denver_buildings_with_parcels as collector
from report_footprint_validation import validate_report_row_footprints


POLYGON = "POLYGON ((-105.0000 39.7000, -104.9990 39.7000, -104.9990 39.7010, -105.0000 39.7010, -105.0000 39.7000))"


class ReportFootprintValidationTests(unittest.TestCase):
    def row(self, area="1000"):
        return {
            "County": "Denver",
            "Parcel Number": "123",
            "Building Footprint": POLYGON,
            "Building Footprint Sq Ft": area,
        }

    def record(self, area=1000):
        return {"building_geometry": POLYGON, "footprint_sqft": area}

    def test_county_source_keeps_bulk_validation_available_when_supabase_fails(self):
        with (
            patch.object(collector, "collect_buildings", side_effect=RuntimeError("database offline")),
            patch.object(collector, "collect_secondary_buildings", return_value=[self.record()]),
            patch("building_footprint_store.save_canonical_footprint", return_value={"canonical_id": 1}),
        ):
            result = validate_report_row_footprints(self.row())

        self.assertEqual(result["status"], "county_only")
        self.assertEqual(result["selected_source"], "county")
        self.assertIn("database offline", result["warnings"][0])

    def test_report_area_over_five_percent_is_a_hard_stop(self):
        with (
            patch.object(collector, "collect_buildings", return_value=[self.record(1200)]),
            patch.object(collector, "collect_secondary_buildings", return_value=[]),
            patch("building_footprint_store.save_canonical_footprint", return_value={"canonical_id": 2}),
        ):
            with self.assertRaisesRegex(RuntimeError, "discrepancy needs attention"):
                validate_report_row_footprints(self.row("1,000"))

    def test_matching_supabase_row_with_no_county_layer_is_informational(self):
        with (
            patch.object(collector, "collect_buildings", return_value=[self.record()]),
            patch.object(collector, "collect_secondary_buildings", return_value=[]),
            patch.object(
                collector,
                "validate_building_footprint_sources",
                return_value={"status": "primary_only", "primary_sqft": 1000},
            ),
            patch("building_footprint_store.save_canonical_footprint", return_value={"canonical_id": 3}),
        ):
            result = validate_report_row_footprints(self.row())

        self.assertEqual(result["status"], "primary_only")
        self.assertIn("only Supabase", result["warnings"][0])

    def test_validated_canonical_record_skips_county_service(self):
        canonical = {
            **self.record(),
            "canonical_id": 42,
            "canonical_status": "validated",
            "canonical_validation": {"status": "validated", "difference_pct": 1.0},
        }
        with (
            patch.object(collector, "collect_buildings", return_value=[canonical]),
            patch.object(collector, "collect_secondary_buildings") as county_lookup,
        ):
            result = validate_report_row_footprints(self.row())

        county_lookup.assert_not_called()
        self.assertEqual(result["selected_source"], "canonical")


if __name__ == "__main__":
    unittest.main()
