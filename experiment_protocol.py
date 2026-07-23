from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExperimentProtocol:
    name: str = "Untitled protocol"
    plate_type: str = ""
    selected_wells: list[str] = field(default_factory=list)
    common_exposure_time_s: float = 0.0

    @property
    def selected_well_count(self) -> int:
        return len(self.selected_wells)

    @property
    def estimated_duration_s(self) -> float:
        return self.selected_well_count * self.common_exposure_time_s

    @property
    def is_valid(self) -> bool:
        return (
            bool(self.plate_type)
            and self.selected_well_count > 0
            and self.common_exposure_time_s > 0
        )