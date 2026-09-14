from __future__ import annotations

import math
from collections.abc import Mapping

from plates.plate_geometry import PlateGeometry

SUPPORTED_WELL_ORDERS = {
    "row",
    "column",
    "serpentine",
    "optimized",
}


def _well_indices(
    plate: PlateGeometry,
    well_name: str,
) -> tuple[int, int]:
    normalized = plate.normalize_well_name(well_name)

    row_index = ord(normalized[0]) - ord("A")
    column_index = int(normalized[1:]) - 1

    return row_index, column_index


def order_wells(
    well_names: list[str],
    plate: PlateGeometry,
    order_mode: str,
    *,
    positions_mm: (
        Mapping[
            str,
            tuple[float, float],
        ]
        | None
    ) = None,
    start_position_mm: tuple[float, float] = (0.0, 0.0),
) -> list[str]:
    if order_mode not in SUPPORTED_WELL_ORDERS:
        raise ValueError(f"Unsupported irradiation order: {order_mode}")

    normalized_wells = [plate.normalize_well_name(well) for well in well_names]

    if len(normalized_wells) != len(set(normalized_wells)):
        raise ValueError("The irradiation sequence contains duplicate wells.")

    def row_key(well: str) -> tuple[int, int]:
        return _well_indices(plate, well)

    if order_mode == "row":
        return sorted(normalized_wells, key=row_key)

    if order_mode == "column":
        return sorted(
            normalized_wells,
            key=lambda well: (
                row_key(well)[1],
                row_key(well)[0],
            ),
        )

    if order_mode == "serpentine":
        return sorted(
            normalized_wells,
            key=lambda well: (
                row_key(well)[0],
                (row_key(well)[1] if row_key(well)[0] % 2 == 0 else -row_key(well)[1]),
            ),
        )

    if positions_mm is None:
        resolved_positions = {
            well: plate.get_relative_position(well) for well in normalized_wells
        }
    else:
        try:
            resolved_positions = {well: positions_mm[well] for well in normalized_wells}
        except KeyError as exc:
            raise ValueError(f"Missing stage position for well {exc.args[0]}.") from exc

    remaining = set(normalized_wells)
    ordered: list[str] = []
    current_position = start_position_mm

    while remaining:
        next_well = min(
            remaining,
            key=lambda well: (
                math.hypot(
                    resolved_positions[well][0] - current_position[0],
                    resolved_positions[well][1] - current_position[1],
                ),
                row_key(well),
            ),
        )

        ordered.append(next_well)
        remaining.remove(next_well)
        current_position = resolved_positions[next_well]

    return ordered
