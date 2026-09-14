from __future__ import annotations

import unittest

from experiment.well_ordering import order_wells
from plates.plate_geometry import PlateGeometry


class WellOrderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plate = PlateGeometry("96-well plate")
        self.wells = [
            "C3",
            "A1",
            "B2",
            "A3",
            "B1",
        ]

    def test_row_order(self) -> None:
        self.assertEqual(
            order_wells(
                self.wells,
                self.plate,
                "row",
            ),
            ["A1", "A3", "B1", "B2", "C3"],
        )

    def test_column_order(self) -> None:
        self.assertEqual(
            order_wells(
                self.wells,
                self.plate,
                "column",
            ),
            ["A1", "B1", "B2", "A3", "C3"],
        )

    def test_serpentine_order(self) -> None:
        self.assertEqual(
            order_wells(
                self.wells,
                self.plate,
                "serpentine",
            ),
            ["A1", "A3", "B2", "B1", "C3"],
        )

    def test_optimized_order_starts_nearest_stage(
        self,
    ) -> None:
        wells = ["A1", "A12", "H1", "H12"]
        positions = {
            "A1": (0.0, 0.0),
            "A12": (0.0, 11.0),
            "H1": (7.0, 0.0),
            "H12": (7.0, 11.0),
        }

        self.assertEqual(
            order_wells(
                wells,
                self.plate,
                "optimized",
                positions_mm=positions,
                start_position_mm=(6.9, 10.9),
            ),
            ["H12", "A12", "A1", "H1"],
        )

    def test_duplicate_wells_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            order_wells(
                ["A1", "A1"],
                self.plate,
                "row",
            )


if __name__ == "__main__":
    unittest.main()
