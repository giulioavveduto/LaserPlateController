from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from experiment.experiment_protocol import ExperimentProtocol, LaserSetpoint
from plates.plate_geometry import PlateGeometry
from plates.well_assignment_widget import WellAssignmentWidget


class LaserAssignmentWidget(QWidget):
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
        group = QGroupBox("Assign laser current to well groups")
        layout = QVBoxLayout(group)

        instruction = QLabel(
            "Only wells selected in the Plate & Timing tab are eligible. "
            "Select wells, choose a current percentage, then click Apply."
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        self.assignment_widget = WellAssignmentWidget(self.plate)
        self.assignment_widget.selection_changed.connect(self._on_selection_changed)
        layout.addWidget(self.assignment_widget)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Laser current:"))

        self.current_spinbox = QSpinBox()
        self.current_spinbox.setRange(0, 100)
        self.current_spinbox.setSingleStep(1)
        self.current_spinbox.setSuffix(" %")
        self.current_spinbox.setValue(30)
        controls.addWidget(self.current_spinbox)

        self.apply_button = QPushButton("Apply to selected wells")
        self.apply_button.clicked.connect(self._apply_current)
        controls.addWidget(self.apply_button)

        self.remove_button = QPushButton("Remove selected overrides")
        self.remove_button.clicked.connect(self._remove_selected_overrides)
        controls.addWidget(self.remove_button)

        controls.addStretch()
        layout.addLayout(controls)

        self.legend_label = QLabel()
        self.legend_label.setWordWrap(True)
        layout.addWidget(self.legend_label)

        self.readiness_label = QLabel()
        layout.addWidget(self.readiness_label)

        main_layout.addWidget(group)
        self.set_eligible_wells(self.protocol.selected_wells)

    def set_eligible_wells(
        self,
        well_names: Iterable[str],
    ) -> None:
        self.assignment_widget.set_eligible_wells(well_names)
        self.refresh()

    def refresh(self) -> None:
        eligible = sorted(self.assignment_widget.eligible_wells)
        setpoints = {well: self.protocol.laser_setpoint_for(well) for well in eligible}

        group_keys = sorted(
            {
                (setpoint.mode, setpoint.value)
                for setpoint in setpoints.values()
                if setpoint is not None
            },
            key=lambda item: (item[0], item[1]),
        )
        colors = {
            key: self.COLORS[index % len(self.COLORS)]
            for index, key in enumerate(group_keys)
        }

        assignments = {}
        for well, setpoint in setpoints.items():
            if setpoint is None:
                continue

            key = (setpoint.mode, setpoint.value)
            assignments[well] = (
                self._format_setpoint(setpoint),
                colors[key],
            )

        self.assignment_widget.set_assignments(assignments)

        legend = [
            self._format_setpoint(LaserSetpoint(mode=mode, value=value))
            for mode, value in group_keys
        ]
        unassigned_count = sum(setpoint is None for setpoint in setpoints.values())

        self.legend_label.setText(
            "Laser groups: " + (", ".join(legend) if legend else "none")
        )

        if eligible and unassigned_count == 0:
            self.readiness_label.setText("Laser assignments complete")
            self.readiness_label.setStyleSheet("font-weight: bold; color: #16803a;")
        else:
            self.readiness_label.setText(
                f"Laser assignments incomplete: "
                f"{unassigned_count} well(s) unassigned"
            )
            self.readiness_label.setStyleSheet("font-weight: bold; color: #a12626;")

        self._on_selection_changed(self.assignment_widget.get_selected_wells())

    def _on_selection_changed(
        self,
        selected_wells: list[str],
    ) -> None:
        enabled = bool(selected_wells)
        self.apply_button.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)

    def _apply_current(self) -> None:
        selected_wells = self.assignment_widget.get_selected_wells()

        if not selected_wells:
            return

        self.protocol.set_laser_setpoint_for_wells(
            selected_wells,
            LaserSetpoint(
                mode="current_percent",
                value=float(self.current_spinbox.value()),
            ),
        )

        self.assignment_widget.clear_selection()
        self.refresh()
        self.protocol_changed.emit()

    def _remove_selected_overrides(self) -> None:
        selected_wells = self.assignment_widget.get_selected_wells()

        for well in selected_wells:
            treatment = self.protocol.well_treatments.get(well)

            if treatment is None:
                continue

            treatment.laser_setpoint = None

            if treatment.exposure_time_s is None:
                self.protocol.well_treatments.pop(well, None)

        self.assignment_widget.clear_selection()
        self.refresh()
        self.protocol_changed.emit()

    @staticmethod
    def _format_setpoint(setpoint: LaserSetpoint) -> str:
        if setpoint.mode == "current_percent":
            return f"{setpoint.value:g}%"

        if setpoint.mode == "power_w":
            return f"{setpoint.value:g} W"

        return f"{setpoint.value:g} W/cm²"
