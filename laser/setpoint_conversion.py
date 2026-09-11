from __future__ import annotations

import math
from dataclasses import dataclass

from experiment.experiment_protocol import LaserSetpoint
from laser.power_calibration import LaserCalibrationStore
from plates.plate_geometry import PlateGeometry


@dataclass(frozen=True)
class ResolvedLaserSetpoint:
    requested_mode: str
    requested_value: float
    calibration_id: str | None

    current_percent: int
    achieved_power_w: float | None
    achieved_irradiance_w_cm2: float | None


def resolve_laser_setpoint(
    setpoint: LaserSetpoint,
    plate: PlateGeometry,
    calibration_store: LaserCalibrationStore,
) -> ResolvedLaserSetpoint:
    if not setpoint.is_valid or not math.isfinite(
        setpoint.value
    ):
        raise ValueError("The laser setpoint is invalid.")

    if setpoint.mode == "current_percent":
        if not float(setpoint.value).is_integer():
            raise ValueError(
                "Laser current must be an integer percentage."
            )

        return ResolvedLaserSetpoint(
            requested_mode=setpoint.mode,
            requested_value=setpoint.value,
            calibration_id=None,
            current_percent=int(setpoint.value),
            achieved_power_w=None,
            achieved_irradiance_w_cm2=None,
        )

    if not setpoint.calibration_id:
        raise ValueError(
            "Power-based assignments require a laser "
            "calibration ID."
        )

    try:
        calibration = calibration_store.get_calibration(
            setpoint.calibration_id
        )
    except KeyError as exc:
        raise ValueError(
            "The laser calibration referenced by this "
            "assignment is not available on this computer."
        ) from exc

    if setpoint.mode == "power_w":
        requested_power_w = setpoint.value
    elif setpoint.mode == "irradiance_w_cm2":
        requested_power_w = (
            setpoint.value * plate.well_area_cm2
        )
    else:
        raise ValueError(
            f"Unsupported laser setpoint mode: {setpoint.mode}"
        )

    current_percent, achieved_power_w = (
        calibration.nearest_current_for_power_w(
            requested_power_w
        )
    )

    achieved_irradiance = (
        achieved_power_w / plate.well_area_cm2
    )

    return ResolvedLaserSetpoint(
        requested_mode=setpoint.mode,
        requested_value=setpoint.value,
        calibration_id=calibration.calibration_id,
        current_percent=current_percent,
        achieved_power_w=achieved_power_w,
        achieved_irradiance_w_cm2=achieved_irradiance,
    )