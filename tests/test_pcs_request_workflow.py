import unittest
from unittest.mock import patch

from assessor_detail import AssessorDetailResult
from pcs_request_workflow import (
    apply_assessor_result_to_row,
    fetch_request_assessor_details,
    filter_selected_rows,
    parse_pcs_request,
)


class PCSRequestValidationTests(unittest.TestCase):
    def test_single_address_requires_exactly_one_parcel(self):
        with self.assertRaisesRegex(ValueError, "exactly one parcel"):
            parse_pcs_request(
                {
                    "selection_type": "address",
                    "properties": [
                        {"county": "Adams", "parcel_id": "1"},
                        {"county": "Adams", "parcel_id": "2"},
                    ],
                }
            )

    def test_map_selection_accepts_multiple_supported_counties(self):
        request = parse_pcs_request(
            {
                "request_id": "PCS-42",
                "selection_type": "map",
                "properties": [
                    {"county": "Boulder County", "parcel_id": "146330324001"},
                    {"county": "Clear Creek", "parcel_id": "195917222900"},
                ],
            }
        )

        self.assertEqual(request.request_id, "PCS-42")
        self.assertEqual([item.county for item in request.properties], ["boulder", "clear_creek"])

    def test_selected_rows_are_bounded_to_request(self):
        request = parse_pcs_request(
            {
                "selection_type": "map",
                "properties": [{"county": "Weld", "parcel_id": "0965-303-00-009"}],
            }
        )
        rows = [
            {"County": "Weld County", "Parcel Number": "096530300009"},
            {"County": "Weld", "Parcel Number": "999999999999"},
        ]

        self.assertEqual(filter_selected_rows(rows, request), rows[:1])


class PCSAssessorIntegrationTests(unittest.TestCase):
    def test_each_selected_parcel_gets_an_independent_lookup(self):
        request = parse_pcs_request(
            {
                "selection_type": "map",
                "properties": [
                    {"county": "Adams", "parcel_id": "A-1"},
                    {"county": "Adams", "parcel_id": "A-2"},
                ],
            }
        )

        def fake_fetch(county, parcels):
            return AssessorDetailResult(county=county, requested_parcels=list(parcels))

        with patch("pcs_request_workflow.fetch_assessor_details", side_effect=fake_fetch) as fetch:
            results = fetch_request_assessor_details(request)

        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(results[("adams", "A1")].requested_parcels, ["A-1"])
        self.assertEqual(results[("adams", "A2")].requested_parcels, ["A-2"])

    def test_assessor_enrichment_only_fills_blank_report_fields(self):
        row = {"Year Built": "2001", "Property Use": ""}
        result = AssessorDetailResult(
            county="weld",
            requested_parcels=["123"],
            records=[
                {
                    "YEARBUILT": "1995",
                    "PRIMARYBLTASDESCRIPTION": "Office",
                    "_assessor_source": "weld_accounts",
                }
            ],
            source_counts={"weld_accounts": 1},
        )

        apply_assessor_result_to_row(row, result)

        self.assertEqual(row["Year Built"], "2001")
        self.assertEqual(row["Property Use"], "Office")
        self.assertEqual(row["Assessor Data Sources"], "weld_accounts")
        self.assertIs(row["_assessor_result"], result)


if __name__ == "__main__":
    unittest.main()
