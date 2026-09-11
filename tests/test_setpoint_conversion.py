from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from experiment.experiment_protocol import LaserSetpoint
from laser.power_calibration import (
    CalibrationPoint,
    LaserCalibrationStore,
)
from laser.setpoint_conversion import (
    resolve_laser_setpoint,
)
from plates.plate_geometry import PlateGeometry


class SetpointConversionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )
        database_path = (
            Path(self.temporary_directory.name)
            / "laser_calibrations.json"
        )
        self.store = LaserCalibrationStore(database_path)
        self.plate = PlateGeometry("96-well plate")

        self.first_calibration = self.store.save_new(
            [
                CalibrationPoint(10, 0.2),
                CalibrationPoint(30, 0.8),
                CalibrationPoint(70, 2.0),
                CalibrationPoint(90, 2.6),
            ]
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_current_percentage_needs_no_calibration(self) -> None:
        result = resolve_laser_setpoint(
            LaserSetpoint(
                mode="current_percent",
                value=35.0,
            ),
            self.plate,
            self.store,
        )

        self.assertEqual(result.current_percent, 35)
        self.assertIsNone(result.achieved_power_w)
        self.assertIsNone(
            result.achieved_irradiance_w_cm2
        )

    def test_power_uses_referenced_calibration_not_active_one(
        self,
    ) -> None:
        self.store.save_new(
            [
                CalibrationPoint(10, 0.4),
                CalibrationPoint(50, 2.0),
                CalibrationPoint(90, 3.6),
            ]
        )

        result = resolve_laser_setpoint(
            LaserSetpoint(
                mode="power_w",
                value=1.44,
                calibration_id=(
                    self.first_calibration.calibration_id
                ),
            ),
            self.plate,
            self.store,
        )

        self.assertEqual(result.current_percent, 51)
        self.assertAlmostEqual(
            result.achieved_power_w,
            1.43,
            places=6,
        )
        self.assertEqual(
            result.calibration_id,
            self.first_calibration.calibration_id,
        )

    def test_irradiance_uses_well_area(self) -> None:
        result = resolve_laser_setpoint(
            LaserSetpoint(
                mode="irradiance_w_cm2",
                value=1.0,
                calibration_id=(
                    self.first_calibration.calibration_id
                ),
            ),
            self.plate,
            self.store,
        )

        self.assertEqual(result.current_percent, 14)
        self.assertAlmostEqual(
            result.achieved_power_w,
            0.32,
            places=6,
        )
        self.assertAlmostEqual(
            result.achieved_irradiance_w_cm2,
            0.32 / self.plate.well_area_cm2,
            places=6,
        )

    def test_power_outside_calibration_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_laser_setpoint(
                LaserSetpoint(
                    mode="power_w",
                    value=3.0,
                    calibration_id=(
                        self.first_calibration.calibration_id
                    ),
                ),
                self.plate,
                self.store,
            )

    def test_power_without_calibration_id_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            resolve_laser_setpoint(
                LaserSetpoint(
                    mode="power_w",
                    value=1.0,
                ),
                self.plate,
                self.store,
            )


if __name__ == "__main__":
    unittest.main()