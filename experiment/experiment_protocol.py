from __future__ import annotations

from dataclasses import dataclass, field
from experiment.well_ordering import (
    SUPPORTED_WELL_ORDERS,
)


@dataclass
class LaserSetpoint:
    mode: str
    value: float
    calibration_id: str | None = None

    SUPPORTED_MODES = {
        "current_percent",
        "power_w",
        "irradiance_w_cm2",
    }

    @property
    def is_valid(self) -> bool:
        if self.mode not in self.SUPPORTED_MODES:
            return False

        if self.mode == "current_percent":
            return 0.0 <= self.value <= 100.0

        return self.value > 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "value": self.value,
            "calibration_id": self.calibration_id,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
    ) -> "LaserSetpoint":
        setpoint = cls(
            mode=str(data.get("mode", "")),
            value=float(data.get("value", 0.0)),
            calibration_id=(
                None
                if data.get("calibration_id") is None
                else str(data["calibration_id"])
            ),
        )

        if not setpoint.is_valid:
            raise ValueError(f"Invalid laser setpoint: {setpoint.to_dict()}")

        return setpoint


@dataclass
class WellTreatment:
    exposure_time_s: float | None = None
    laser_setpoint: LaserSetpoint | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "exposure_time_s": self.exposure_time_s,
            "laser_setpoint": (
                None if self.laser_setpoint is None else self.laser_setpoint.to_dict()
            ),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
    ) -> "WellTreatment":
        exposure_value = data.get("exposure_time_s")
        laser_data = data.get("laser_setpoint")

        if laser_data is not None and not isinstance(laser_data, dict):
            raise ValueError("The well laser setpoint must be a JSON object or null.")

        treatment = cls(
            exposure_time_s=(None if exposure_value is None else float(exposure_value)),
            laser_setpoint=(
                None if laser_data is None else LaserSetpoint.from_dict(laser_data)
            ),
        )

        if treatment.exposure_time_s is not None and treatment.exposure_time_s <= 0:
            raise ValueError("A well-specific exposure time must be greater than zero.")

        return treatment


@dataclass
class ExperimentProtocol:
    name: str = "Untitled protocol"
    plate_type: str = ""
    selected_wells: list[str] = field(default_factory=list)
    irradiation_order: str = "row"

    common_exposure_time_s: float = 0.0
    default_laser_setpoint: LaserSetpoint | None = None

    well_treatments: dict[str, WellTreatment] = field(default_factory=dict)

    @property
    def selected_well_count(self) -> int:
        return len(self.selected_wells)

    def exposure_time_for(self, well_name: str) -> float:
        treatment = self.well_treatments.get(well_name)

        if treatment is not None and treatment.exposure_time_s is not None:
            return treatment.exposure_time_s

        return self.common_exposure_time_s

    def laser_setpoint_for(
        self,
        well_name: str,
    ) -> LaserSetpoint | None:
        treatment = self.well_treatments.get(well_name)

        if treatment is not None and treatment.laser_setpoint is not None:
            return treatment.laser_setpoint

        return self.default_laser_setpoint

    @property
    def estimated_duration_s(self) -> float:
        return sum(
            self.exposure_time_for(well_name) for well_name in self.selected_wells
        )

    @property
    def is_valid(self) -> bool:
        return (
            bool(self.plate_type)
            and self.irradiation_order in SUPPORTED_WELL_ORDERS
            and self.selected_well_count > 0
            and all(
                self.exposure_time_for(well_name) > 0
                for well_name in self.selected_wells
            )
        )

    @property
    def is_laser_ready(self) -> bool:
        if not self.is_valid:
            return False

        return all(
            (setpoint := self.laser_setpoint_for(well_name)) is not None
            and setpoint.is_valid
            for well_name in self.selected_wells
        )

    def set_exposure_time_for_wells(
        self,
        well_names: list[str],
        exposure_time_s: float,
    ) -> None:
        if exposure_time_s <= 0:
            raise ValueError("Exposure time must be greater than zero.")

        for well_name in well_names:
            treatment = self.well_treatments.setdefault(
                well_name,
                WellTreatment(),
            )
            treatment.exposure_time_s = exposure_time_s

    def set_laser_setpoint_for_wells(
        self,
        well_names: list[str],
        setpoint: LaserSetpoint,
    ) -> None:
        if not setpoint.is_valid:
            raise ValueError("The laser setpoint is invalid.")

        for well_name in well_names:
            treatment = self.well_treatments.setdefault(
                well_name,
                WellTreatment(),
            )
            treatment.laser_setpoint = LaserSetpoint(
                mode=setpoint.mode,
                value=setpoint.value,
                calibration_id=setpoint.calibration_id,
            )

    def remove_unselected_treatments(self) -> None:
        selected = set(self.selected_wells)

        self.well_treatments = {
            well_name: treatment
            for well_name, treatment in self.well_treatments.items()
            if well_name in selected
        }

    def to_dict(self) -> dict[str, object]:
        self.remove_unselected_treatments()

        return {
            "format_version": 2,
            "name": self.name,
            "plate_type": self.plate_type,
            "selected_wells": list(self.selected_wells),
            "irradiation_order": self.irradiation_order,
            "common_exposure_time_s": self.common_exposure_time_s,
            "default_laser_setpoint": (
                None
                if self.default_laser_setpoint is None
                else self.default_laser_setpoint.to_dict()
            ),
            "well_treatments": {
                well_name: treatment.to_dict()
                for well_name, treatment in self.well_treatments.items()
            },
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
    ) -> "ExperimentProtocol":
        format_version = data.get("format_version")

        if format_version == 1:
            return cls(
                name=str(data.get("name", "Untitled protocol")),
                plate_type=str(data.get("plate_type", "")),
                selected_wells=[str(well) for well in data.get("selected_wells", [])],
                common_exposure_time_s=float(data.get("common_exposure_time_s", 0.0)),
            )

        if format_version != 2:
            raise ValueError(
                "Unsupported protocol format version: " f"{format_version}"
            )

        default_laser_data = data.get("default_laser_setpoint")
        treatment_data = data.get("well_treatments", {})

        if default_laser_data is not None and not isinstance(default_laser_data, dict):
            raise ValueError("The default laser setpoint must be an object or null.")

        if not isinstance(treatment_data, dict):
            raise ValueError("The well treatments must be a JSON object.")

        protocol = cls(
            name=str(data.get("name", "Untitled protocol")),
            plate_type=str(data.get("plate_type", "")),
            selected_wells=[str(well) for well in data.get("selected_wells", [])],
            irradiation_order=str(data.get("irradiation_order", "row")),
            common_exposure_time_s=float(data.get("common_exposure_time_s", 0.0)),
            default_laser_setpoint=(
                None
                if default_laser_data is None
                else LaserSetpoint.from_dict(default_laser_data)
            ),
            well_treatments={
                str(well_name): WellTreatment.from_dict(treatment)
                for well_name, treatment in treatment_data.items()
                if isinstance(treatment, dict)
            },
        )

        if protocol.irradiation_order not in SUPPORTED_WELL_ORDERS:
            raise ValueError(
                "Unsupported irradiation order: " f"{protocol.irradiation_order}"
            )

        protocol.remove_unselected_treatments()
        return protocol
