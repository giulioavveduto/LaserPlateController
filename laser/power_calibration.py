from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class CalibrationPoint:
    current_percent: int
    power_w: float

    def __post_init__(self) -> None:
        if (
            type(self.current_percent) is not int
            or not 0 <= self.current_percent <= 100
        ):
            raise ValueError(
                "Calibration current must be an integer " "from 0 to 100%."
            )

        if not math.isfinite(self.power_w):
            raise ValueError("Measured power must be finite.")

        if self.current_percent == 0:
            if self.power_w != 0.0:
                raise ValueError("The 0% calibration point must be 0 W.")
        elif self.power_w <= 0.0:
            raise ValueError(
                "Measured power above 0% current must be " "greater than zero."
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "current_percent": self.current_percent,
            "power_w": self.power_w,
        }


@dataclass(frozen=True)
class LaserPowerCalibration:
    calibration_id: str
    created_at_utc: str
    points: tuple[CalibrationPoint, ...]

    def __post_init__(self) -> None:
        if not self.calibration_id.strip():
            raise ValueError("Calibration ID cannot be empty.")

        ordered_points = tuple(
            sorted(
                self.points,
                key=lambda point: point.current_percent,
            )
        )
        object.__setattr__(self, "points", ordered_points)

        positive_points = tuple(
            point for point in ordered_points if point.current_percent > 0
        )

        if len(positive_points) < 2:
            raise ValueError(
                "At least two calibration points above 0% " "are required."
            )

        currents = [point.current_percent for point in ordered_points]
        powers = [point.power_w for point in ordered_points]

        if len(set(currents)) != len(currents):
            raise ValueError("Each current percentage may appear only once.")

        if any(right <= left for left, right in zip(powers, powers[1:])):
            raise ValueError(
                "Measured power must increase strictly with " "current percentage."
            )

    @classmethod
    def create(
        cls,
        points: Iterable[CalibrationPoint],
    ) -> "LaserPowerCalibration":
        timestamp = (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )

        return cls(
            calibration_id=uuid.uuid4().hex,
            created_at_utc=timestamp,
            points=tuple(points),
        )

    @property
    def interpolation_points(
        self,
    ) -> tuple[CalibrationPoint, ...]:
        return tuple(point for point in self.points if point.current_percent > 0)

    @property
    def minimum_current_percent(self) -> int:
        return self.interpolation_points[0].current_percent

    @property
    def maximum_current_percent(self) -> int:
        return self.interpolation_points[-1].current_percent

    @property
    def minimum_power_w(self) -> float:
        return self.interpolation_points[0].power_w

    @property
    def maximum_power_w(self) -> float:
        return self.interpolation_points[-1].power_w

    @staticmethod
    def _interpolate(
        value: float,
        x_values: list[float],
        y_values: list[float],
    ) -> float:
        if value == x_values[-1]:
            return y_values[-1]

        for index in range(len(x_values) - 1):
            x_left = x_values[index]
            x_right = x_values[index + 1]

            if x_left <= value <= x_right:
                fraction = (value - x_left) / (x_right - x_left)
                return y_values[index] + fraction * (
                    y_values[index + 1] - y_values[index]
                )

        raise ValueError("The requested value is outside the calibrated range.")

    def power_for_current_percent(
        self,
        current_percent: float,
    ) -> float:
        if not math.isfinite(current_percent):
            raise ValueError("Current percentage must be finite.")

        if current_percent == 0:
            return 0.0

        if not (
            self.minimum_current_percent
            <= current_percent
            <= self.maximum_current_percent
        ):
            raise ValueError(
                "Current percentage is outside the calibrated range "
                f"{self.minimum_current_percent}–"
                f"{self.maximum_current_percent}%."
            )

        return self._interpolate(
            current_percent,
            [float(point.current_percent) for point in self.interpolation_points],
            [point.power_w for point in self.interpolation_points],
        )

    def current_percent_for_power_w(
        self,
        power_w: float,
    ) -> float:
        if not math.isfinite(power_w) or power_w < 0.0:
            raise ValueError("Requested power must be finite and non-negative.")

        if power_w == 0:
            return 0.0

        if not (self.minimum_power_w <= power_w <= self.maximum_power_w):
            raise ValueError(
                "Requested power is outside the calibrated range "
                f"{self.minimum_power_w:g}–"
                f"{self.maximum_power_w:g} W."
            )

        return self._interpolate(
            power_w,
            [point.power_w for point in self.interpolation_points],
            [float(point.current_percent) for point in self.interpolation_points],
        )

    def nearest_current_for_power_w(
        self,
        power_w: float,
    ) -> tuple[int, float]:
        exact_percent = self.current_percent_for_power_w(power_w)

        if exact_percent == 0:
            return 0, 0.0

        candidates = {
            max(
                self.minimum_current_percent,
                math.floor(exact_percent),
            ),
            min(
                self.maximum_current_percent,
                math.ceil(exact_percent),
            ),
        }

        evaluated = [
            (
                candidate,
                self.power_for_current_percent(candidate),
            )
            for candidate in candidates
        ]

        return min(
            evaluated,
            key=lambda result: (
                abs(result[1] - power_w),
                result[0],
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "calibration_id": self.calibration_id,
            "created_at_utc": self.created_at_utc,
            "points": [point.to_dict() for point in self.points],
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
    ) -> "LaserPowerCalibration":
        raw_points = data.get("points")

        if not isinstance(raw_points, list):
            raise ValueError("Calibration points must be stored as a list.")

        points: list[CalibrationPoint] = []

        for raw_point in raw_points:
            if not isinstance(raw_point, dict):
                raise ValueError("Each calibration point must be an object.")

            points.append(
                CalibrationPoint(
                    current_percent=int(raw_point["current_percent"]),
                    power_w=float(raw_point["power_w"]),
                )
            )

        return cls(
            calibration_id=str(data.get("calibration_id", "")),
            created_at_utc=str(data.get("created_at_utc", "")),
            points=tuple(points),
        )


class LaserCalibrationStore:
    FORMAT_VERSION = 1

    def __init__(
        self,
        database_path: str | Path | None = None,
    ) -> None:
        if database_path is None:
            database_path = (
                Path(__file__).resolve().parents[1]
                / "calibration"
                / "laser_power_calibrations.json"
            )

        self.database_path = Path(database_path)

    def _empty_database(self) -> dict[str, object]:
        return {
            "format_version": self.FORMAT_VERSION,
            "active_calibration_id": None,
            "calibrations": {},
        }

    def _load_database(self) -> dict[str, object]:
        if not self.database_path.exists():
            return self._empty_database()

        data = json.loads(self.database_path.read_text(encoding="utf-8"))

        if not isinstance(data, dict):
            raise ValueError("Laser calibration database must contain an object.")

        if data.get("format_version") != self.FORMAT_VERSION:
            raise ValueError("Unsupported laser calibration database version.")

        if not isinstance(data.get("calibrations"), dict):
            raise ValueError("Laser calibration history must be an object.")

        return data

    def get_calibration(
        self,
        calibration_id: str,
    ) -> LaserPowerCalibration:
        database = self._load_database()
        calibrations = database["calibrations"]

        raw_calibration = calibrations.get(calibration_id)

        if not isinstance(raw_calibration, dict):
            raise KeyError(f"Unknown laser calibration: {calibration_id}")

        return LaserPowerCalibration.from_dict(raw_calibration)

    def get_active(self) -> LaserPowerCalibration | None:
        database = self._load_database()
        active_id = database.get("active_calibration_id")

        if active_id is None:
            return None

        return self.get_calibration(str(active_id))

    def save_new(
        self,
        points: Iterable[CalibrationPoint],
    ) -> LaserPowerCalibration:
        calibration = LaserPowerCalibration.create(points)
        database = self._load_database()
        calibrations = database["calibrations"]

        calibrations[calibration.calibration_id] = calibration.to_dict()
        database["active_calibration_id"] = calibration.calibration_id

        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = self.database_path.with_name(self.database_path.name + ".tmp")
        temporary_path.write_text(
            json.dumps(database, indent=4),
            encoding="utf-8",
        )
        temporary_path.replace(self.database_path)

        return calibration
