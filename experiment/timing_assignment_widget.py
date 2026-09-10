from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from experiment.experiment_protocol import (
    ExperimentProtocol,
)
from plates.plate_geometry import PlateGeometry
from plates.well_assignment_widget import WellAssignmentWidget


class TimingAssignmentWidget(QWidget):
    protocol_changed = Signal()

    COLORS = [
        "#b7dcff",
        "#ffd6a5",
        "#c8e6c9",
        "#e1bee7",
        "#fff59d",
        "#ffccbc",
        "#b2dfdb",
        "#d7ccc8",
    ]

    def __init__(
        self,
        protocol: ExperimentProtocol,
        plate: PlateGeometry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.protocol = protocol
        self.plate = plate

        main_layout = QVBoxLayout(self)

        assignment_group = QGroupBox("Assign durations to well groups")
        assignment_layout = QVBoxLayout(assignment_group)

        instruction = QLabel(
            "Select one or more eligible wells, choose an exposure "
            "duration, then click Apply. Use “Select all eligible” "
            "to assign the same duration to every well."
        )
        instruction.setWordWrap(True)
        assignment_layout.addWidget(instruction)

        self.assignment_widget = WellAssignmentWidget(self.plate)
        self.assignment_widget.selection_changed.connect(
            self._on_assignment_selection_changed
        )
        assignment_layout.addWidget(self.assignment_widget)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(QLabel("Group duration:"))

        self.group_duration_spinbox = QDoubleSpinBox()
        self.group_duration_spinbox.setRange(0.1, 86400.0)
        self.group_duration_spinbox.setDecimals(1)
        self.group_duration_spinbox.setSingleStep(1.0)
        self.group_duration_spinbox.setSuffix(" s")
        self.group_duration_spinbox.setValue(
            max(0.1, self.protocol.common_exposure_time_s)
        )
        controls_layout.addWidget(self.group_duration_spinbox)

        self.apply_button = QPushButton("Apply to selected wells")
        self.apply_button.clicked.connect(self._apply_group_duration)
        controls_layout.addWidget(self.apply_button)

        self.reset_button = QPushButton("Remove selected overrides")
        self.reset_button.clicked.connect(self._reset_selected_to_global)
        controls_layout.addWidget(self.reset_button)

        controls_layout.addStretch()
        assignment_layout.addLayout(controls_layout)

        self.legend_label = QLabel()
        self.legend_label.setWordWrap(True)
        assignment_layout.addWidget(self.legend_label)

        main_layout.addWidget(assignment_group)

        self.set_eligible_wells(self.protocol.selected_wells)

    def set_eligible_wells(
        self,
        well_names: Iterable[str],
    ) -> None:
        self.assignment_widget.set_eligible_wells(well_names)
        self.refresh()

    def refresh(self) -> None:

        eligible_wells = sorted(self.assignment_widget.eligible_wells)

        durations = {
            well: self.protocol.exposure_time_for(well) for well in eligible_wells
        }

        unique_durations = sorted(set(durations.values()))
        duration_colors = {
            duration: self.COLORS[index % len(self.COLORS)]
            for index, duration in enumerate(unique_durations)
        }

        assignments = {
            well: (
                self._format_duration_short(duration),
                duration_colors[duration],
            )
            for well, duration in durations.items()
        }

        self.assignment_widget.set_assignments(assignments)

        if unique_durations:
            legend_parts = [
                self._format_duration_long(duration) for duration in unique_durations
            ]
            self.legend_label.setText("Timing groups: " + ", ".join(legend_parts))
        else:
            self.legend_label.setText("Timing groups: none")

        self._on_assignment_selection_changed(
            self.assignment_widget.get_selected_wells()
        )

    def _on_assignment_selection_changed(
        self,
        selected_wells: list[str],
    ) -> None:
        has_selection = bool(selected_wells)
        self.apply_button.setEnabled(has_selection)
        self.reset_button.setEnabled(has_selection)

    def _apply_group_duration(self) -> None:
        selected_wells = self.assignment_widget.get_selected_wells()

        if not selected_wells:
            return

        self.protocol.set_exposure_time_for_wells(
            selected_wells,
            self.group_duration_spinbox.value(),
        )

        self.assignment_widget.clear_selection()
        self.refresh()
        self.protocol_changed.emit()

    def _reset_selected_to_global(self) -> None:
        selected_wells = self.assignment_widget.get_selected_wells()

        for well in selected_wells:
            treatment = self.protocol.well_treatments.get(well)

            if treatment is None:
                continue

            treatment.exposure_time_s = None

            if treatment.laser_setpoint is None:
                self.protocol.well_treatments.pop(
                    well,
                    None,
                )

        self.assignment_widget.clear_selection()
        self.refresh()
        self.protocol_changed.emit()

    @staticmethod
    def _format_duration_short(duration_s: float) -> str:
        if duration_s >= 60 and duration_s % 60 == 0:
            return f"{duration_s / 60:g}m"

        return f"{duration_s:g}s"

    @staticmethod
    def _format_duration_long(duration_s: float) -> str:
        if duration_s >= 60 and duration_s % 60 == 0:
            return f"{duration_s / 60:g} min"

        return f"{duration_s:g} s"
