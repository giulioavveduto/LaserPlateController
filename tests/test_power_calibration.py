from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from laser.power_calibration import (
    CalibrationPoint,
    LaserCalibrationStore,
    LaserPowerCalibration,
)


def make_points() -> list[CalibrationPoint]:
    return [
        CalibrationPoint(10, 0.2),
        CalibrationPoint(30, 0.8),
        CalibrationPoint(70, 2.0),
        CalibrationPoint(90, 2.6),
    ]


class LaserPowerCalibrationTests(unittest.TestCase):
    def test_piecewise_interpolation_in_both_directions(self) -> None:
        calibration = LaserPowerCalibration.create(
            make_points()
        )

        self.assertAlmostEqual(
            calibration.power_for_current_percent(20),
            0.5,
        )
        self.assertAlmostEqual(
            calibration.current_percent_for_power_w(1.4),
            50.0,
        )

    def test_zero_represents_emission_off(self) -> None:
        calibration = LaserPowerCalibration.create(
            make_points()
        )

        self.assertEqual(
            calibration.power_for_current_percent(0),
            0.0,
        )
        self.assertEqual(
            calibration.current_percent_for_power_w(0),
            0.0,
        )

    def test_extrapolation_is_rejected(self) -> None:
        calibration = LaserPowerCalibration.create(
            make_points()
        )

        with self.assertRaises(ValueError):
            calibration.power_for_current_percent(5)

        with self.assertRaises(ValueError):
            calibration.power_for_current_percent(95)

        with self.assertRaises(ValueError):
            calibration.current_percent_for_power_w(0.1)

        with self.assertRaises(ValueError):
            calibration.current_percent_for_power_w(3.0)

    def test_non_monotonic_power_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            LaserPowerCalibration.create(
                [
                    CalibrationPoint(10, 0.3),
                    CalibrationPoint(30, 0.2),
                ]
            )

    def test_new_calibration_replaces_active_set_but_keeps_history(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = (
                Path(directory)
                / "laser_power_calibrations.json"
            )
            store = LaserCalibrationStore(database_path)

            first = store.save_new(make_points())
            second = store.save_new(
                [
                    CalibrationPoint(20, 0.4),
                    CalibrationPoint(50, 1.5),
                    CalibrationPoint(80, 2.7),
                ]
            )

            active = store.get_active()

            self.assertIsNotNone(active)
            self.assertEqual(
                active.calibration_id,
                second.calibration_id,
            )
            self.assertEqual(
                [point.current_percent for point in active.points],
                [20, 50, 80],
            )

            historical = store.get_calibration(
                first.calibration_id
            )
            self.assertEqual(
                [point.current_percent for point in historical.points],
                [10, 30, 70, 90],
            )

    def test_integer_current_is_selected_by_nearest_power(self) -> None:
        calibration = LaserPowerCalibration.create(
            make_points()
        )

        current, achieved_power = (
            calibration.nearest_current_for_power_w(1.44)
        )

        self.assertEqual(current, 51)
        self.assertAlmostEqual(
            achieved_power,
            1.43,
            places=6,
        )
    def test_zero_point_enables_low_range_interpolation(
        self,
    ) -> None:
        calibration = LaserPowerCalibration.create(
            [
                CalibrationPoint(0, 0.0),
                CalibrationPoint(10, 0.2),
                CalibrationPoint(30, 0.8),
            ]
        )

        self.assertAlmostEqual(
            calibration.power_for_current_percent(5),
            0.1,
        )
        self.assertAlmostEqual(
            calibration.current_percent_for_power_w(0.1),
            5.0,
        )

    def test_zero_percent_requires_zero_power(self) -> None:
        with self.assertRaises(ValueError):
            CalibrationPoint(0, 0.1)

        with self.assertRaises(ValueError):
            CalibrationPoint(10, 0.0)


if __name__ == "__main__":
    unittest.main()