from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CalibrationManager:
    def __init__(
        self,
        calibration_path: str | Path | None = None,
        instrument_name: str = "NABI Laser Stage",
    ) -> None:
        if calibration_path is None:
            calibration_path = Path(__file__).with_name("calibrations.json")

        self.calibration_path = Path(calibration_path)
        self.instrument_name = instrument_name

        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self.calibration_path.exists():
            self._data = {}
            return

        try:
            with self.calibration_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                loaded_data = json.load(file)

            if not isinstance(loaded_data, dict):
                raise ValueError("The calibration file must contain a JSON object.")

            self._data = loaded_data

        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid calibration JSON file: {exc}") from exc

    def _save(self) -> None:
        self.calibration_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = self.calibration_path.with_suffix(".json.tmp")

        with temporary_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                self._data,
                file,
                indent=4,
                sort_keys=True,
            )

        temporary_path.replace(self.calibration_path)

    def set_a1(
        self,
        plate_name: str,
        x_mm: float,
        y_mm: float,
    ) -> None:
        if not plate_name.strip():
            raise ValueError("Plate name cannot be empty.")

        if x_mm < 0 or y_mm < 0:
            raise ValueError("A1 coordinates cannot be negative.")

        instrument_data = self._data.setdefault(
            self.instrument_name,
            {},
        )

        instrument_data[plate_name] = {
            "a1_x_mm": float(x_mm),
            "a1_y_mm": float(y_mm),
        }

        self._save()

    def get_a1(
        self,
        plate_name: str,
    ) -> tuple[float, float] | None:
        calibration = self._data.get(self.instrument_name, {}).get(plate_name)

        if calibration is None:
            return None

        return (
            float(calibration["a1_x_mm"]),
            float(calibration["a1_y_mm"]),
        )

    def is_calibrated(self, plate_name: str) -> bool:
        return self.get_a1(plate_name) is not None

    def remove_calibration(self, plate_name: str) -> bool:
        instrument_data = self._data.get(
            self.instrument_name,
            {},
        )

        if plate_name not in instrument_data:
            return False

        del instrument_data[plate_name]

        if not instrument_data:
            self._data.pop(self.instrument_name, None)

        self._save()
        return True

    def get_absolute_well_position(
        self,
        plate_name: str,
        relative_x_mm: float,
        relative_y_mm: float,
    ) -> tuple[float, float]:
        a1_position = self.get_a1(plate_name)

        if a1_position is None:
            raise RuntimeError(f"{plate_name} has not been calibrated.")

        a1_x_mm, a1_y_mm = a1_position

        return (
            a1_x_mm + relative_x_mm,
            a1_y_mm + relative_y_mm,
        )
