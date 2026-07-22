import unittest

from county_discovery_health import aggregate_county_status, aggregate_sample_status


class CountyDiscoveryHealthAggregationTests(unittest.TestCase):
    def test_two_passing_samples_are_healthy(self):
        self.assertEqual(
            aggregate_sample_status([{"status": "healthy"}, {"status": "healthy"}]),
            "healthy",
        )

    def test_one_passing_sample_is_degraded(self):
        self.assertEqual(
            aggregate_sample_status([{"status": "healthy"}, {"status": "failed"}]),
            "degraded",
        )

    def test_no_passing_samples_are_failed(self):
        self.assertEqual(
            aggregate_sample_status([{"status": "failed"}, {"status": "failed"}]),
            "failed",
        )

    def test_overall_status_uses_most_severe_county_status(self):
        self.assertEqual(
            aggregate_county_status(
                [{"status": "healthy"}, {"status": "degraded"}]
            ),
            "degraded",
        )
        self.assertEqual(
            aggregate_county_status(
                [{"status": "healthy"}, {"status": "failed"}]
            ),
            "failed",
        )


if __name__ == "__main__":
    unittest.main()
