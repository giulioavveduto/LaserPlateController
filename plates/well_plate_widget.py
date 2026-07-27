from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, QTimer, Signal
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


class WellButton(QPushButton):
    drag_started = Signal(str, bool)
    drag_entered = Signal(str)
    drag_finished = Signal()

    def __init__(self, well_name: str) -> None:
        super().__init__(well_name)

        self.well_name = well_name
        self.execution_state: str | None = None
        self.pulse_highlighted = False
        self.setCheckable(True)
        self.setMinimumSize(30, 30)
        self.setMaximumSize(46, 46)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.toggled.connect(self.update_style)
        self.update_style()

    def update_style(self) -> None:
        if self.execution_state == "completed":
            background_color = "#79c98b"
            border_color = "#287a3b"
            font_weight = "bold"
            hover_rule = ""

        elif self.execution_state == "current":
                background_color = (
                    "#fff0b3"
                    if self.pulse_highlighted
                    else "#f28c00"
                )
                border_color = "#a64b00"
                font_weight = "bold"
                hover_rule = ""

        elif self.execution_state == "pending":
            background_color = "#d9dde2"
            border_color = "#777d85"
            font_weight = "normal"
            hover_rule = ""

        elif self.isChecked():
            background_color = "#7fb7e6"
            border_color = "#1f5f99"
            font_weight = "bold"
            hover_rule = ""

        else:
            background_color = "#f4f4f4"
            border_color = "#777777"
            font_weight = "normal"
            hover_rule = """
                QPushButton:hover {
                    background-color: #dcecff;
                }
            """

        self.setStyleSheet(
            f"""
            QPushButton {{
                border-radius: 15px;
                border: 2px solid {border_color};
                background-color: {background_color};
                font-weight: {font_weight};
            }}

            {hover_rule}
            """
        )

    def set_execution_state(
        self,
        execution_state: str | None,
    ) -> None:
        valid_states = {
            None,
            "pending",
            "current",
            "completed",
        }

        if execution_state not in valid_states:
            raise ValueError(
                f"Invalid well execution state: {execution_state}"
            )

        self.execution_state = execution_state
        self.update_style()

    def set_pulse_highlighted(self, highlighted: bool) -> None:
        if self.pulse_highlighted == highlighted:
            return

        self.pulse_highlighted = highlighted

        if self.execution_state == "current":
            self.update_style()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            target_state = not self.isChecked()

            self.setChecked(target_state)
            self.drag_started.emit(self.well_name, target_state)

            event.accept()
            return

        super().mousePressEvent(event)

    def enterEvent(self, event: QEnterEvent) -> None:
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.drag_entered.emit(self.well_name)

        super().enterEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_finished.emit()
            event.accept()
            return

        super().mouseReleaseEvent(event)


class WellPlateWidget(QWidget):
    selection_changed = Signal(list)

    def __init__(
        self,
        plate: PlateGeometry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.plate = plate
        self.well_buttons: dict[str, WellButton] = {}
        self.drag_target_state: bool | None = None
        self.pulsing_well: str | None = None
        self.pulse_phase = False

        self.pulse_timer = QTimer(self)
        self.pulse_timer.setInterval(500)
        self.pulse_timer.timeout.connect(self._advance_pulse)        
        main_layout = QVBoxLayout(self)

        controls_layout = QGridLayout()

        self.selected_count_label = QLabel("Selected wells: 0")
        controls_layout.addWidget(self.selected_count_label, 0, 0)

        select_all_button = QPushButton("Select all")
        select_all_button.clicked.connect(self.select_all)
        controls_layout.addWidget(select_all_button, 0, 1)

        clear_button = QPushButton("Clear selection")
        clear_button.clicked.connect(self.clear_selection)
        controls_layout.addWidget(clear_button, 0, 2)

        invert_button = QPushButton("Invert selection")
        invert_button.clicked.connect(self.invert_selection)
        controls_layout.addWidget(invert_button, 0, 3)

        main_layout.addLayout(controls_layout)

        self.plate_layout = QGridLayout()
        self.plate_layout.setHorizontalSpacing(8)
        self.plate_layout.setVerticalSpacing(8)

        self._create_plate_grid()

        main_layout.addLayout(self.plate_layout)
        main_layout.addStretch()

    def _create_plate_grid(self) -> None:
        corner_label = QLabel("")
        self.plate_layout.addWidget(corner_label, 0, 0)

        for column in range(1, self.plate.columns + 1):
            column_button = QPushButton(str(column))
            column_button.setToolTip(f"Select or deselect column {column}")
            column_button.setFixedHeight(28)
            column_button.clicked.connect(
                lambda checked=False, current_column=column: self.toggle_column(
                    current_column
                )
            )

            self.plate_layout.addWidget(
                column_button,
                0,
                column,
            )

        for row_index in range(self.plate.rows):
            row_letter = chr(ord("A") + row_index)

            row_button = QPushButton(row_letter)
            row_button.setToolTip(f"Select or deselect row {row_letter}")
            row_button.setFixedWidth(34)
            row_button.clicked.connect(
                lambda checked=False, current_row=row_letter: self.toggle_row(
                    current_row
                )
            )

            self.plate_layout.addWidget(
                row_button,
                row_index + 1,
                0,
            )

            for column in range(1, self.plate.columns + 1):
                well_name = f"{row_letter}{column}"
                button = WellButton(well_name)

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

    def _start_drag(
        self,
        well_name: str,
        target_state: bool,
    ) -> None:
        self.drag_target_state = target_state

        button = self.well_buttons[well_name]
        button.setChecked(target_state)

    def _apply_drag_selection(
        self,
        well_name: str,
    ) -> None:
        if self.drag_target_state is None:
            return

        button = self.well_buttons[well_name]
        button.setChecked(self.drag_target_state)

    def _finish_drag(self) -> None:
        self.drag_target_state = None

    def set_current_well_pulsing(
        self,
        well_name: str | None,
        pulsing: bool,
    ) -> None:
        normalized_well = (
            self.plate.normalize_well_name(well_name)
            if well_name is not None
            else None
        )

        if (
            pulsing
            and normalized_well == self.pulsing_well
            and self.pulse_timer.isActive()
        ):
            return

        self.stop_execution_pulse()

        if (
            not pulsing
            or normalized_well is None
            or normalized_well not in self.well_buttons
        ):
            return

        self.pulsing_well = normalized_well
        self.pulse_phase = False
        self.pulse_timer.start()

    def stop_execution_pulse(self) -> None:
        self.pulse_timer.stop()

        if self.pulsing_well is not None:
            button = self.well_buttons.get(self.pulsing_well)

            if button is not None:
                button.set_pulse_highlighted(False)

        self.pulsing_well = None
        self.pulse_phase = False

    def _advance_pulse(self) -> None:
        if self.pulsing_well is None:
            self.stop_execution_pulse()
            return

        button = self.well_buttons.get(self.pulsing_well)

        if button is None or button.execution_state != "current":
            self.stop_execution_pulse()
            return

        self.pulse_phase = not self.pulse_phase
        button.set_pulse_highlighted(self.pulse_phase)

    def prepare_execution(
        self,
        well_names: Iterable[str],
    ) -> None:
        self.stop_execution_pulse()

        execution_wells = {
            self.plate.normalize_well_name(well_name)
            for well_name in well_names
        }

        for well_name, button in self.well_buttons.items():
            if well_name in execution_wells:
                button.set_execution_state("pending")
            else:
                button.set_execution_state(None)

    def update_execution_display(
        self,
        *,
        current_well: str | None,
        completed_wells: Iterable[str],
    ) -> None:
        normalized_completed = {
            self.plate.normalize_well_name(well_name)
            for well_name in completed_wells
        }

        normalized_current = (
            self.plate.normalize_well_name(current_well)
            if current_well is not None
            else None
        )

        for well_name, button in self.well_buttons.items():
            if well_name in normalized_completed:
                button.set_execution_state("completed")
            elif well_name == normalized_current:
                button.set_execution_state("current")
            elif button.execution_state is not None:
                button.set_execution_state("pending")

    def clear_execution_display(self) -> None:
        self.stop_execution_pulse()
        for button in self.well_buttons.values():
            button.set_execution_state(None)        

    def get_selected_wells(self) -> list[str]:
        return [
            well_name
            for well_name, button in self.well_buttons.items()
            if button.isChecked()
        ]

    def set_selected_wells(
        self,
        well_names: Iterable[str],
    ) -> None:
        normalized_wells = {
            self.plate.normalize_well_name(well_name) for well_name in well_names
        }

        for well_name, button in self.well_buttons.items():
            button.setChecked(well_name in normalized_wells)

        self._emit_selection()

    def toggle_row(self, row_letter: str) -> None:
        row_wells = [
            f"{row_letter}{column}" for column in range(1, self.plate.columns + 1)
        ]

        all_selected = all(self.well_buttons[well].isChecked() for well in row_wells)

        target_state = not all_selected

        for well in row_wells:
            self.well_buttons[well].setChecked(target_state)

        self._emit_selection()

    def toggle_column(self, column: int) -> None:
        column_wells = [
            f"{chr(ord('A') + row_index)}{column}"
            for row_index in range(self.plate.rows)
        ]

        all_selected = all(self.well_buttons[well].isChecked() for well in column_wells)

        target_state = not all_selected

        for well in column_wells:
            self.well_buttons[well].setChecked(target_state)

        self._emit_selection()

    def select_all(self) -> None:
        for button in self.well_buttons.values():
            button.setChecked(True)

        self._emit_selection()

    def clear_selection(self) -> None:
        for button in self.well_buttons.values():
            button.setChecked(False)

        self._emit_selection()

    def invert_selection(self) -> None:
        for button in self.well_buttons.values():
            button.setChecked(not button.isChecked())

        self._emit_selection()

    def _emit_selection(self) -> None:
        selected_wells = self.get_selected_wells()

        self.selected_count_label.setText(f"Selected wells: {len(selected_wells)}")
        self.selection_changed.emit(selected_wells)
