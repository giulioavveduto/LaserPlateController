from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WellParameters:
    exposure_time_s: float
    laser_power_w_cm2: float | None = None

    def validate(self) -> list[str]:
        errors: list[str] = []

        if self.exposure_time_s <= 0:
            errors.append("Exposure time must be greater than zero.")

        if (
            self.laser_power_w_cm2 is not None
            and self.laser_power_w_cm2 <= 0
        ):
            errors.append("Laser power must be greater than zero.")

        return errors


@dataclass
class ExperimentProtocol:
    plate_name: str
    selected_wells: list[str] = field(default_factory=list)
    well_parameters: dict[str, WellParameters] = field(
        default_factory=dict
    )

    preheat_time_s: float = 0.0
    movement_time_per_well_s: float = 2.0
    settling_time_per_well_s: float = 0.0
    inter_well_delay_s: float = 0.0

    def set_selected_wells(self, well_names: list[str]) -> None:
        self.selected_wells = list(dict.fromkeys(well_names))

        selected_set = set(self.selected_wells)

        self.well_parameters = {
            well_name: parameters
            for well_name, parameters in self.well_parameters.items()
            if well_name in selected_set
        }

    def assign_common_exposure_time(
        self,
        exposure_time_s: float,
    ) -> None:
        for well_name in self.selected_wells:
            existing = self.well_parameters.get(well_name)

            self.well_parameters[well_name] = WellParameters(
                exposure_time_s=exposure_time_s,
                laser_power_w_cm2=(
                    existing.laser_power_w_cm2
                    if existing is not None
                    else None
                ),
            )

    def assign_common_laser_power(
        self,
        laser_power_w_cm2: float,
    ) -> None:
        for well_name in self.selected_wells:
            existing = self.well_parameters.get(well_name)

            self.well_parameters[well_name] = WellParameters(
                exposure_time_s=(
                    existing.exposure_time_s
                    if existing is not None
                    else 0.0
                ),
                laser_power_w_cm2=laser_power_w_cm2,
            )

    def get_total_exposure_time_s(self) -> float:
        return sum(
            self.well_parameters[well_name].exposure_time_s
            for well_name in self.selected_wells
            if well_name in self.well_parameters
        )

    def get_estimated_total_duration_s(self) -> float:
        number_of_wells = len(self.selected_wells)

        if number_of_wells == 0:
            return self.preheat_time_s

        per_well_overhead_s = (
            self.movement_time_per_well_s
            + self.settling_time_per_well_s
        )

        between_well_delays_s = (
            max(number_of_wells - 1, 0)
            * self.inter_well_delay_s
        )

        return (
            self.preheat_time_s
            + self.get_total_exposure_time_s()
            + number_of_wells * per_well_overhead_s
            + between_well_delays_s
        )

    def get_well_exposure_time_s(self, well_name: str) -> float:
        if well_name not in self.well_parameters:
            raise KeyError(
                f"No exposure parameters assigned to well {well_name}."
            )

        return self.well_parameters[well_name].exposure_time_s

    def validate(self) -> list[str]:
        errors: list[str] = []

        if not self.selected_wells:
            errors.append("No wells are selected.")

        if self.preheat_time_s < 0:
            errors.append("Preheat time cannot be negative.")

        if self.movement_time_per_well_s < 0:
            errors.append(
                "Movement-time estimate cannot be negative."
            )

        if self.settling_time_per_well_s < 0:
            errors.append("Settling time cannot be negative.")

        if self.inter_well_delay_s < 0:
            errors.append("Inter-well delay cannot be negative.")

        for well_name in self.selected_wells:
            parameters = self.well_parameters.get(well_name)

            if parameters is None:
                errors.append(
                    f"Well {well_name} has no assigned parameters."
                )
                continue

            for error in parameters.validate():
                errors.append(f"Well {well_name}: {error}")

        return errors


def format_duration(total_seconds: float) -> str:
    total_seconds_int = max(0, round(total_seconds))

    hours, remainder = divmod(total_seconds_int, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        return f"{hours:d} h {minutes:02d} min {seconds:02d} s"

    if minutes > 0:
        return f"{minutes:d} min {seconds:02d} s"

    return f"{seconds:d} s"