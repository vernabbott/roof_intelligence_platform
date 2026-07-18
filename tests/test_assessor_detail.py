import unittest
from unittest.mock import patch

import assessor_detail
import collect_denver_buildings_with_parcels as collector
from county_config import ASSESSOR_SOURCES, AssessorSource, assessor_sources


class AssessorConfigurationTests(unittest.TestCase):
    def test_remaining_nine_counties_are_configured(self):
        self.assertEqual(
            set(ASSESSOR_SOURCES),
            {
                "denver",
                "adams",
                "arapahoe",
                "boulder",
                "broomfield",
                "clear_creek",
                "douglas",
                "jefferson",
                "larimer",
                "weld",
            },
        )

    def test_every_county_has_a_parcel_scoped_entry_source(self):
        for county, sources in ASSESSOR_SOURCES.items():
            self.assertTrue(sources, county)
            self.assertEqual(sources[0].lookup_by, "parcel", county)
            self.assertTrue(sources[0].lookup_field, county)

    def test_clear_creek_aliases_are_supported(self):
        self.assertEqual(assessor_sources("Clear Creek"), assessor_sources("clear_creek"))
        self.assertEqual(assessor_sources("ClearCreek"), assessor_sources("clear_creek"))


class AssessorLookupTests(unittest.TestCase):
    def test_bulk_enrichment_uses_one_bounded_lookup_per_matched_parcel(self):
        records = [
            {"SCHEDNUM": "123", "year_built": ""},
            {"SCHEDNUM": "123", "year_built": ""},
        ]
        result = assessor_detail.AssessorDetailResult(
            county="denver",
            requested_parcels=["123"],
            records=[{"ORIG_YOC": 1999}],
            source_counts={"denver_property": 1},
        )
        with patch.object(collector, "fetch_assessor_details", return_value=result) as fetch:
            collector.enrich_with_assessor(records, "denver")

        fetch.assert_called_once_with("denver", ["123"])
        self.assertEqual([record["year_built"] for record in records], [1999, 1999])

    def test_arcgis_query_is_bounded_to_exact_identifiers(self):
        source = AssessorSource(
            key="test",
            label="Test",
            kind="arcgis",
            url="https://example.test/FeatureServer/0/query",
            role="combined",
            lookup_by="parcel",
            lookup_field="PARCEL_ID",
        )
        with patch.object(
            assessor_detail,
            "_json_request",
            return_value={"features": [{"attributes": {"PARCEL_ID": "12-34"}}]},
        ) as request:
            records = assessor_detail.query_arcgis_source(source, ["12-34"])

        self.assertEqual(records, [{"PARCEL_ID": "12-34"}])
        params = request.call_args.kwargs["params"]
        self.assertIn("PARCEL_ID IN", params["where"])
        self.assertIn("12-34", params["where"])
        self.assertIn("1234", params["where"])
        self.assertNotIn("1=1", params["where"])
        self.assertEqual(params["returnGeometry"], "false")

    def test_account_sources_are_queried_after_parcel_account_lookup(self):
        def fake_query(source, identifiers):
            if source.key == "boulder_parcel_accounts":
                self.assertEqual(list(identifiers), ["123456789012"])
                return [{"ParcelNo": "123456789012", "AccountNo": "R0123456"}]
            if source.key == "boulder_building_info":
                self.assertEqual(list(identifiers), ["R0123456"])
                return [{"AccountNo": "R0123456", "YearBuilt": 1998}]
            self.fail(source.key)

        with patch.object(assessor_detail, "query_source", side_effect=fake_query):
            result = assessor_detail.fetch_assessor_details("boulder", ["123456789012"])

        self.assertEqual(result.source_counts["boulder_parcel_accounts"], 1)
        self.assertEqual(result.source_counts["boulder_building_info"], 1)
        self.assertEqual(result.records[-1]["YearBuilt"], 1998)

    def test_douglas_query_uses_exact_term_filter(self):
        source = assessor_sources("douglas")[0]
        with patch.object(
            assessor_detail,
            "_json_request",
            return_value={"hits": {"hits": [{"_source": {"state_parcel_number": "222901312050"}}]}},
        ) as request:
            records = assessor_detail.query_douglas_source(source, ["2229-01-3-12-050"])

        self.assertEqual(records[0]["state_parcel_number"], "222901312050")
        payload = request.call_args.kwargs["payload"]
        self.assertEqual(
            payload,
            {"query": {"bool": {"filter": [{"terms": {"state_parcel_number": ["222901312050"]}}]}}},
        )

    def test_arapahoe_lookup_generates_hyphenated_parcel_variant(self):
        source = assessor_sources("arapahoe")[0]
        with patch.object(
            assessor_detail,
            "_json_request",
            return_value={"features": []},
        ) as request:
            assessor_detail.query_arcgis_source(source, ["207534436001"])

        self.assertIn("2075-34-4-36-001", request.call_args.kwargs["params"]["where"])

    def test_lookup_rejects_unbounded_request(self):
        with self.assertRaisesRegex(ValueError, "At least one parcel"):
            assessor_detail.fetch_assessor_details("weld", [])

    def test_canonical_report_values_support_nested_county_records(self):
        values = assessor_detail.canonical_report_values(
            [{"buildings": [{"actual_year_built": 1997, "construction_type": "Masonry"}]}]
        )

        self.assertEqual(values["Year Built"], 1997)
        self.assertEqual(values["Construction Type"], "Masonry")

    def test_explicit_ground_floor_area_can_validate_footprint(self):
        result = assessor_detail.validate_assessor_footprint(
            10000, [{"ground_floor_area": 10400, "gross_area": 25000}]
        )

        self.assertEqual(result["status"], "validated")
        self.assertEqual(result["assessor_sqft"], 10400)

    def test_gross_area_is_not_treated_as_footprint(self):
        result = assessor_detail.validate_assessor_footprint(
            10000, [{"gross_area": 25000, "total_sqft": 25000}]
        )

        self.assertEqual(result["status"], "not_comparable")
        self.assertIn("gross", result["reason"])

    def test_explicit_footprint_over_five_percent_is_discrepancy(self):
        result = assessor_detail.validate_assessor_footprint(
            10000, [{"building_footprint_sqft": 11000}]
        )

        self.assertEqual(result["status"], "discrepancy")
        self.assertEqual(result["difference_pct"], 10)


if __name__ == "__main__":
    unittest.main()
