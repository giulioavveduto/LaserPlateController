from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QEnterEvent, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from plates.plate_geometry import PlateGeometry


class AssignmentWellButton(QPushButton):
    drag_started = Signal(str, bool)
    drag_entered = Signal(str)
    drag_finished = Signal()

    def __init__(self, well_name: str) -> None:
        super().__init__(well_name)

        self.well_name = well_name
        self.eligible = False
        self.assignment_label: str | None = None
        self.assignment_color: str | None = None

        self.setCheckable(True)
        self.setMinimumSize(34, 38)
        self.setMaximumSize(56, 52)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self.toggled.connect(self.update_style)
        self.set_eligible(False)

    def set_eligible(self, eligible: bool) -> None:
        self.eligible = eligible
        self.setEnabled(eligible)

        if not eligible:
            self.setChecked(False)

        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if eligible
            else Qt.CursorShape.ArrowCursor
        )
        self.update_style()

    def set_assignment(
        self,
        label: str | None,
        color: str | None,
    ) -> None:
        self.assignment_label = label
        self.assignment_color = color

        self.setText(self.well_name if label is None else f"{self.well_name}\n{label}")

        self.setToolTip(
            "Not selected for irradiation"
            if not self.eligible
            else (
                "No treatment assigned"
                if label is None
                else f"Assigned treatment: {label}"
            )
        )

        self.update_style()

    def update_style(self) -> None:
        if not self.eligible:
            background = "#e1e3e6"
            border = "#a0a4aa"
            text_color = "#8a8d92"
            border_width = 1

        else:
            background = self.assignment_color or "#fff4cc"
            text_color = "#202124"

            if self.isChecked():
                border = "#1565c0"
                border_width = 4
            else:
                border = "#666666"
                border_width = 2

        self.setStyleSheet(f"""
            QPushButton {{
                border-radius: 15px;
                border: {border_width}px solid {border};
                background-color: {background};
                color: {text_color};
                font-weight: bold;
                font-size: 10px;
            }}
            """)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.eligible and event.button() == Qt.MouseButton.LeftButton:
            target_state = not self.isChecked()
            self.setChecked(target_state)
            self.drag_started.emit(
                self.well_name,
                target_state,
            )
            event.accept()
            return

        super().mousePressEvent(event)

    def enterEvent(self, event: QEnterEvent) -> None:
        if self.eligible and QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.drag_entered.emit(self.well_name)

        super().enterEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_finished.emit()
            event.accept()
            return

        super().mouseReleaseEvent(event)


class WellAssignmentWidget(QWidget):
    selection_changed = Signal(list)

    def __init__(
        self,
        plate: PlateGeometry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.plate = plate
        self.well_buttons: dict[
            str,
            AssignmentWellButton,
        ] = {}

        self.eligible_wells: set[str] = set()
        self.assignments: dict[
            str,
            tuple[str, str],
        ] = {}

        self.drag_target_state: bool | None = None
        self.suppress_selection_signal = False

        main_layout = QVBoxLayout(self)

        controls_layout = QGridLayout()

        self.selection_label = QLabel("Selected for assignment: 0")
        controls_layout.addWidget(
            self.selection_label,
            0,
            0,
        )

        select_all_button = QPushButton("Select all eligible")
        select_all_button.clicked.connect(self.select_all_eligible)
        controls_layout.addWidget(
            select_all_button,
            0,
            1,
        )

        clear_button = QPushButton("Clear assignment selection")
        clear_button.clicked.connect(self.clear_selection)
        controls_layout.addWidget(clear_button, 0, 2)

        main_layout.addLayout(controls_layout)

        self.plate_layout = QGridLayout()
        self.plate_layout.setHorizontalSpacing(8)
        self.plate_layout.setVerticalSpacing(8)

        self.row_buttons: dict[str, QPushButton] = {}
        self.column_buttons: dict[int, QPushButton] = {}

        self._create_plate_grid()

        main_layout.addLayout(self.plate_layout)
        main_layout.addStretch()

    def _create_plate_grid(self) -> None:
        self.plate_layout.addWidget(QLabel(""), 0, 0)

        for column in range(1, self.plate.columns + 1):
            button = QPushButton(str(column))
            button.setFixedHeight(28)
            button.setToolTip(f"Select eligible wells in column {column}")
            button.clicked.connect(
                lambda checked=False, value=column: self.toggle_column(value)
            )

            self.column_buttons[column] = button
            self.plate_layout.addWidget(
                button,
                0,
                column,
            )

        for row_index in range(self.plate.rows):
            row_letter = chr(ord("A") + row_index)

            row_button = QPushButton(row_letter)
            row_button.setFixedWidth(34)
            row_button.setToolTip(f"Select eligible wells in row {row_letter}")
            row_button.clicked.connect(
                lambda checked=False, value=row_letter: self.toggle_row(value)
            )

            self.row_buttons[row_letter] = row_button
            self.plate_layout.addWidget(
                row_button,
                row_index + 1,
                0,
            )

            for column in range(1, self.plate.columns + 1):
                well_name = f"{row_letter}{column}"
                button = AssignmentWellButton(well_name)

                button.drag_started.connect(self._start_drag)
                button.drag_entered.connect(self._apply_drag_selection)
                button.drag_finished.connect(self._finish_drag)
                button.toggled.connect(self._emit_selection)

                self.well_buttons[well_name] = button
                self.plate_layout.addWidget(
                    button,
                    row_index + 1,
                    column,
                )

    def set_eligible_wells(
        self,
        well_names: Iterable[str],
    ) -> None:
        normalized = {self.plate.normalize_well_name(well) for well in well_names}

        self.eligible_wells = normalized
        self.assignments = {
            well: assignment
            for well, assignment in self.assignments.items()
            if well in normalized
        }

        self.suppress_selection_signal = True

        try:
            for well_name, button in self.well_buttons.items():
                button.set_eligible(well_name in normalized)

                assignment = self.assignments.get(well_name)
                button.set_assignment(
                    None if assignment is None else assignment[0],
                    None if assignment is None else assignment[1],
                )
        finally:
            self.suppress_selection_signal = False

        self._update_header_buttons()
        self._emit_selection()

    def set_assignments(
        self,
        assignments: dict[str, tuple[str, str]],
    ) -> None:
        self.assignments = {
            self.plate.normalize_well_name(well): assignment
            for well, assignment in assignments.items()
            if self.plate.normalize_well_name(well) in self.eligible_wells
        }

        for well_name, button in self.well_buttons.items():
            assignment = self.assignments.get(well_name)
            button.set_assignment(
                None if assignment is None else assignment[0],
                None if assignment is None else assignment[1],
            )

    def get_selected_wells(self) -> list[str]:
        return [
            well
            for well, button in self.well_buttons.items()
            if button.isChecked() and button.eligible
        ]

    def select_all_eligible(self) -> None:
        self._set_checked_wells(
            self.eligible_wells,
            True,
        )

    def clear_selection(self) -> None:
        self._set_checked_wells(
            self.eligible_wells,
            False,
        )

    def toggle_row(self, row_letter: str) -> None:
        wells = [well for well in self.eligible_wells if well.startswith(row_letter)]
        self._toggle_well_group(wells)

    def toggle_column(self, column: int) -> None:
        wells = [well for well in self.eligible_wells if int(well[1:]) == column]
        self._toggle_well_group(wells)

    def _toggle_well_group(
        self,
        wells: Iterable[str],
    ) -> None:
        wells = list(wells)

        if not wells:
            return

        target_state = not all(self.well_buttons[well].isChecked() for well in wells)
        self._set_checked_wells(
            wells,
            target_state,
        )

    def _set_checked_wells(
        self,
        wells: Iterable[str],
        checked: bool,
    ) -> None:
        self.suppress_selection_signal = True

        try:
            for well in wells:
                self.well_buttons[well].setChecked(checked)
        finally:
            self.suppress_selection_signal = False

        self._emit_selection()

    def _start_drag(
        self,
        well_name: str,
        target_state: bool,
    ) -> None:
        self.drag_target_state = target_state
        self.well_buttons[well_name].setChecked(target_state)

    def _apply_drag_selection(
        self,
        well_name: str,
    ) -> None:
        if self.drag_target_state is None:
            return

        button = self.well_buttons[well_name]

        if button.eligible:
            button.setChecked(self.drag_target_state)

    def _finish_drag(self) -> None:
        self.drag_target_state = None
        self._emit_selection()

    def _update_header_buttons(self) -> None:
        for row_letter, button in self.row_buttons.items():
            button.setEnabled(
                any(well.startswith(row_letter) for well in self.eligible_wells)
            )

        for column, button in self.column_buttons.items():
            button.setEnabled(
                any(int(well[1:]) == column for well in self.eligible_wells)
            )

    def _emit_selection(self) -> None:
        if self.suppress_selection_signal:
            return

        selected = self.get_selected_wells()
        self.selection_label.setText(f"Selected for assignment: {len(selected)}")
        self.selection_changed.emit(selected)
