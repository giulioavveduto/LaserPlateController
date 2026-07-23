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


    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": 1,
            "name": self.name,
            "plate_type": self.plate_type,
            "selected_wells": list(self.selected_wells),
            "common_exposure_time_s": self.common_exposure_time_s,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
    ) -> "ExperimentProtocol":
        format_version = data.get("format_version")

        if format_version != 1:
            raise ValueError(
                f"Unsupported protocol format version: {format_version}"
            )

        return cls(
            name=str(data.get("name", "Untitled protocol")),
            plate_type=str(data.get("plate_type", "")),
            selected_wells=list(data.get("selected_wells", [])),
            common_exposure_time_s=float(
                data.get("common_exposure_time_s", 0.0)
            ),
        )

