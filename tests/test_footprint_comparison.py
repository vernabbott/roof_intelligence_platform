import unittest

import assessor_detail
import collect_county_buildings_with_parcels as collector
from footprint_comparison import compare_microsoft_to_county


GEOMETRY = (
    "POLYGON ((-105 40, -104.9999 40, -104.9999 40.0001, "
    "-105 40.0001, -105 40))"
)


class DirectionalFootprintComparisonTests(unittest.TestCase):
    def test_microsoft_larger_is_accepted(self):
        result = compare_microsoft_to_county(1200, 1000)

        self.assertEqual(result["status"], "validated")
        self.assertEqual(result["resolution"], "microsoft_preferred")
        self.assertEqual(result["county_excess_pct"], 0.0)

    def test_county_less_than_five_percent_larger_is_accepted(self):
        self.assertEqual(compare_microsoft_to_county(1000, 1049)["status"], "validated")

    def test_county_exactly_five_percent_larger_is_accepted(self):
        result = compare_microsoft_to_county(1000, 1050)

        self.assertEqual(result["status"], "validated")
        self.assertEqual(result["county_excess_pct"], 5.0)

    def test_county_more_than_five_percent_larger_is_discrepancy(self):
        result = compare_microsoft_to_county(1000, 1051)

        self.assertEqual(result["status"], "discrepancy")
        self.assertEqual(result["county_excess_pct"], 5.1)
        self.assertNotIn("resolution", result)

    def test_gis_validation_uses_shared_directional_rule(self):
        result = collector.validate_building_footprint_sources(
            {"building_geometry": GEOMETRY, "footprint_sqft": 1200},
            [{"building_geometry": GEOMETRY, "footprint_sqft": 1000}],
        )

        self.assertEqual(result["status"], "validated")
        self.assertEqual(result["comparison_rule"], "county_exceeds_microsoft")
        self.assertEqual(result["primary_sqft"], 1200)
        self.assertEqual(result["secondary_sqft"], 1000)

    def test_assessor_validation_uses_shared_directional_rule(self):
        result = assessor_detail.validate_assessor_footprint(
            1200, [{"ground_floor_area": 1000}]
        )

        self.assertEqual(result["status"], "validated")
        self.assertEqual(result["comparison_rule"], "county_exceeds_microsoft")
        self.assertEqual(result["assessor_sqft"], 1000)


if __name__ == "__main__":
    unittest.main()
