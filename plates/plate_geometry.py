from __future__ import annotations

import json
import re
from pathlib import Path


class PlateGeometry:
    def __init__(
        self,
        plate_name: str,
        database_path: str | Path | None = None,
    ) -> None:
        if database_path is None:
            database_path = Path(__file__).with_name("default_plates.json")

        self.database_path = Path(database_path)

        with self.database_path.open("r", encoding="utf-8") as file:
            database = json.load(file)

        if plate_name not in database:
            available = ", ".join(database.keys())
            raise ValueError(
                f"Unknown plate type: {plate_name}. "
                f"Available plate types: {available}"
            )

        plate_data = database[plate_name]

        self.name = plate_name
        self.rows = int(plate_data["rows"])
        self.columns = int(plate_data["columns"])
        self.pitch_x_mm = float(plate_data["pitch_x_mm"])
        self.pitch_y_mm = float(plate_data["pitch_y_mm"])
        self.well_diameter_mm = float(plate_data["well_diameter_mm"])

    def normalize_well_name(self, well_name: str) -> str:
        normalized = well_name.strip().upper()

        match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", normalized)
        if match is None:
            raise ValueError(
                f"Invalid well name: {well_name}. "
                "Expected a format such as A1, B3 or H12."
            )

        row_letters, column_text = match.groups()

        if len(row_letters) != 1:
            raise ValueError(
                f"Invalid row in well name: {well_name}. "
                "This plate supports single-letter row names."
            )

        row_index = ord(row_letters) - ord("A")
        column_index = int(column_text) - 1

        if row_index < 0 or row_index >= self.rows:
            last_row = chr(ord("A") + self.rows - 1)
            raise ValueError(
                f"Well {well_name} is outside the plate. "
                f"Valid rows are A to {last_row}."
            )

        if column_index < 0 or column_index >= self.columns:
            raise ValueError(
                f"Well {well_name} is outside the plate. "
                f"Valid columns are 1 to {self.columns}."
            )

        return f"{row_letters}{column_index + 1}"

    def get_relative_position(
        self,
        well_name: str,
    ) -> tuple[float, float]:
        normalized = self.normalize_well_name(well_name)

        row_letter = normalized[0]
        column_number = int(normalized[1:])

        row_index = ord(row_letter) - ord("A")
        column_index = column_number - 1

        x_mm = column_index * self.pitch_x_mm
        y_mm = row_index * self.pitch_y_mm

        return x_mm, y_mm

    def get_all_wells(self) -> list[str]:
        wells: list[str] = []

        for row_index in range(self.rows):
            row_letter = chr(ord("A") + row_index)

            for column_number in range(1, self.columns + 1):
                wells.append(f"{row_letter}{column_number}")

        return wells
