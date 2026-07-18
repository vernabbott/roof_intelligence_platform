from __future__ import annotations

import unittest
from unittest.mock import patch

import geopandas as gpd
from shapely.geometry import MultiPolygon, Point, Polygon

import import_building_footprints as importer


class StableExternalIdTests(unittest.TestCase):
    def test_id_is_independent_of_ring_start_and_orientation(self) -> None:
        first = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        reordered = Polygon([(1, 1), (1, 0), (0, 0), (0, 1), (1, 1)])

        self.assertEqual(
            importer.stable_external_id(first),
            importer.stable_external_id(reordered),
        )

    def test_different_geometry_has_different_id(self) -> None:
        first = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        second = Polygon([(0, 0), (2, 0), (2, 1), (0, 1), (0, 0)])

        self.assertNotEqual(
            importer.stable_external_id(first),
            importer.stable_external_id(second),
        )


class ConflictSafeInsertTests(unittest.TestCase):
    def test_insert_uses_source_external_id_conflict_protection(self) -> None:
        polygon = MultiPolygon([Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])])
        buildings = gpd.GeoDataFrame(
            [{
                "external_id": "msft-co-test",
                "state": "CO",
                "county": "Denver",
                "municipality": None,
                "geometry": polygon,
                "centroid": Point(0.5, 0.5),
                "footprint_sqft": 100.0,
                "perimeter_ft": 40.0,
                "source": importer.SOURCE_NAME,
            }],
            geometry="geometry",
            crs=importer.OUTPUT_CRS,
        )
        calls: list[tuple[str, int]] = []

        class FakeCursor:
            rowcount = 0

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class FakeRawConnection:
            def cursor(self):
                return FakeCursor()

        class FakeConnection:
            connection = FakeRawConnection()

        def fake_execute_values(cursor, sql, rows, **_kwargs):
            calls.append((sql, len(rows)))
            cursor.rowcount = len(rows)

        with patch.object(importer, "execute_values", fake_execute_values):
            inserted = importer.write_to_postgis(buildings, FakeConnection(), chunk_size=5000)

        self.assertEqual(inserted, 1)
        self.assertEqual(calls[0][1], 1)
        self.assertIn('INSERT INTO "building_footprints"', calls[0][0])
        self.assertIn("ON CONFLICT (source, external_id) DO NOTHING", calls[0][0])


if __name__ == "__main__":
    unittest.main()
