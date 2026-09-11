from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from experiment.experiment_protocol import ExperimentProtocol, LaserSetpoint
from plates.plate_geometry import PlateGeometry
from plates.well_assignment_widget import WellAssignmentWidget
from laser.power_calibration import LaserCalibrationStore
from laser.setpoint_conversion import resolve_laser_setpoint

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
        calibration_store: LaserCalibrationStore,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.protocol = protocol
        self.plate = plate
        self.calibration_store = calibration_store
        self._setpoint_available = True

        main_layout = QVBoxLayout(self)
        group = QGroupBox("Assign laser exposure to well groups")
        layout = QVBoxLayout(group)

        instruction = QLabel(
            "Only wells selected in the Well selection tab are eligible. "
            "Choose %, W, or W/cm², select wells, then click Apply. "
            "Power-based modes use the active laser calibration."
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        self.assignment_widget = WellAssignmentWidget(
            self.plate
        )
        self.assignment_widget.selection_changed.connect(
            self._on_selection_changed
        )

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Setpoint:"))

        self.mode_combo = QComboBox()
        self.mode_combo.addItem(
            "Current percentage (%)",
            "current_percent",
        )
        self.mode_combo.addItem(
            "Optical power (W)",
            "power_w",
        )
        self.mode_combo.addItem(
            "Power density (W/cm²)",
            "irradiance_w_cm2",
        )
        self.mode_combo.currentIndexChanged.connect(
            self._on_mode_changed
        )
        controls.addWidget(self.mode_combo)

        self.value_spinbox = QDoubleSpinBox()
        self.value_spinbox.valueChanged.connect(
            self._update_conversion_preview
        )
        controls.addWidget(self.value_spinbox)

        self.apply_button = QPushButton(
            "Apply to selected wells"
        )
        self.apply_button.clicked.connect(
            self._apply_setpoint
        )
        controls.addWidget(self.apply_button)

        self.remove_button = QPushButton(
            "Remove selected overrides"
        )
        self.remove_button.clicked.connect(
            self._remove_selected_overrides
        )
        controls.addWidget(self.remove_button)

        controls.addStretch()
        layout.addLayout(controls)

        self.conversion_label = QLabel()
        self.conversion_label.setWordWrap(True)
        layout.addWidget(self.conversion_label)
        layout.addWidget(self.assignment_widget)

        self.legend_label = QLabel()
        self.legend_label.setWordWrap(True)
        layout.addWidget(self.legend_label)

        self.readiness_label = QLabel()
        layout.addWidget(self.readiness_label)

        main_layout.addWidget(group)
        self._on_mode_changed()
        self.set_eligible_wells(
            self.protocol.selected_wells
        )

        self._on_mode_changed()
        self.set_eligible_wells(
            self.protocol.selected_wells
        )

    def _editor_setpoint(self) -> LaserSetpoint:
        mode = str(self.mode_combo.currentData())
        calibration_id = None

        if mode != "current_percent":
            calibration = (
                self.calibration_store.get_active()
            )

            if calibration is None:
                raise ValueError(
                    "Create a laser power calibration first."
                )

            calibration_id = calibration.calibration_id

        return LaserSetpoint(
            mode=mode,
            value=float(self.value_spinbox.value()),
            calibration_id=calibration_id,
        )

    def _on_mode_changed(self, *_args) -> None:
        mode = str(self.mode_combo.currentData())

        self.value_spinbox.blockSignals(True)

        try:
            if mode == "current_percent":
                self.value_spinbox.setDecimals(0)
                self.value_spinbox.setRange(0, 100)
                self.value_spinbox.setSingleStep(1)
                self.value_spinbox.setSuffix(" %")
                self.value_spinbox.setValue(30)
                self.value_spinbox.setEnabled(True)
                self._setpoint_available = True

            else:
                calibration = (
                    self.calibration_store.get_active()
                )

                if calibration is None:
                    raise ValueError(
                        "No active laser calibration."
                    )

                self.value_spinbox.setDecimals(4)
                self.value_spinbox.setSingleStep(0.01)

                if mode == "power_w":
                    minimum = max(
                        calibration.minimum_power_w,
                        0.0001,
                    )
                    maximum = calibration.maximum_power_w
                    suffix = " W"
                else:
                    minimum = max(
                        calibration.minimum_power_w
                        / self.plate.well_area_cm2,
                        0.0001,
                    )
                    maximum = (
                        calibration.maximum_power_w
                        / self.plate.well_area_cm2
                    )
                    suffix = " W/cm²"

                self.value_spinbox.setRange(
                    minimum,
                    maximum,
                )
                self.value_spinbox.setSuffix(suffix)
                self.value_spinbox.setValue(minimum)
                self.value_spinbox.setEnabled(True)
                self._setpoint_available = True

        except (OSError, ValueError, KeyError) as exc:
            self.value_spinbox.setRange(0.0, 0.0)
            self.value_spinbox.setEnabled(False)
            self._setpoint_available = False
            self.conversion_label.setText(str(exc))
            self.conversion_label.setStyleSheet(
                "font-weight: bold; color: #a12626;"
            )

        finally:
            self.value_spinbox.blockSignals(False)

        self._update_conversion_preview()
        self._on_selection_changed(
            self.assignment_widget.get_selected_wells()
        )

    def _update_conversion_preview(
        self,
        *_args,
    ) -> None:
        if not self._setpoint_available:
            return

        try:
            setpoint = self._editor_setpoint()

            if setpoint.mode == "current_percent":
                self.conversion_label.setText(
                    "Controller command: "
                    f"{int(setpoint.value)}%. "
                    "No power calibration is required."
                )
                self.conversion_label.setStyleSheet("")
                return

            resolved = resolve_laser_setpoint(
                setpoint,
                self.plate,
                self.calibration_store,
            )

            if setpoint.mode == "power_w":
                requested_text = (
                    f"{setpoint.value:.4f} W"
                )
            else:
                requested_text = (
                    f"{setpoint.value:.4f} W/cm²"
                )

            self.conversion_label.setText(
                f"Requested: {requested_text} → "
                f"controller command: "
                f"{resolved.current_percent}% → "
                f"achieved: "
                f"{resolved.achieved_power_w:.4f} W, "
                f"{resolved.achieved_irradiance_w_cm2:.4f} W/cm²"
            )
            self.conversion_label.setStyleSheet(
                "color: #16803a;"
            )

        except (OSError, ValueError, KeyError) as exc:
            self.conversion_label.setText(str(exc))
            self.conversion_label.setStyleSheet(
                "font-weight: bold; color: #a12626;"
            )

    def refresh_calibration(self) -> None:
        self._on_mode_changed()
        self.refresh()

    def set_eligible_wells(
        self,
        well_names: Iterable[str],
    ) -> None:
        self.assignment_widget.set_eligible_wells(well_names)
        self.refresh()

    def refresh(self) -> None:
        eligible = sorted(
            self.assignment_widget.eligible_wells
        )
        setpoints = {
            well: self.protocol.laser_setpoint_for(well)
            for well in eligible
        }

        group_setpoints = {}

        for setpoint in setpoints.values():
            if setpoint is None:
                continue

            key = (
                setpoint.mode,
                setpoint.value,
                setpoint.calibration_id or "",
            )
            group_setpoints.setdefault(key, setpoint)

        group_keys = sorted(group_setpoints)
        colors = {
            key: self.COLORS[index % len(self.COLORS)]
            for index, key in enumerate(group_keys)
        }
        formatted_groups = {
            key: self._format_setpoint(setpoint)
            for key, setpoint in group_setpoints.items()
        }

        assignments = {}
        invalid_count = 0

        for well, setpoint in setpoints.items():
            if setpoint is None:
                continue

            key = (
                setpoint.mode,
                setpoint.value,
                setpoint.calibration_id or "",
            )
            assignments[well] = (
                formatted_groups[key],
                colors[key],
            )

            try:
                resolve_laser_setpoint(
                    setpoint,
                    self.plate,
                    self.calibration_store,
                )
            except (OSError, ValueError, KeyError):
                invalid_count += 1

        self.assignment_widget.set_assignments(
            assignments
        )

        legend = [
            formatted_groups[key]
            for key in group_keys
        ]
        unassigned_count = sum(
            setpoint is None
            for setpoint in setpoints.values()
        )

        self.legend_label.setText(
            "Laser groups: "
            + (", ".join(legend) if legend else "none")
        )

        if (
            eligible
            and unassigned_count == 0
            and invalid_count == 0
        ):
            self.readiness_label.setText(
                "Laser assignments complete"
            )
            self.readiness_label.setStyleSheet(
                "font-weight: bold; color: #16803a;"
            )
        else:
            self.readiness_label.setText(
                "Laser assignments incomplete: "
                f"{unassigned_count} unassigned, "
                f"{invalid_count} invalid"
            )
            self.readiness_label.setStyleSheet(
                "font-weight: bold; color: #a12626;"
            )

        self._on_selection_changed(
            self.assignment_widget.get_selected_wells()
        )

    def _on_selection_changed(
        self,
        selected_wells: list[str],
    ) -> None:
        has_selection = bool(selected_wells)

        self.apply_button.setEnabled(
            has_selection and self._setpoint_available
        )
        self.remove_button.setEnabled(has_selection)

    def _apply_setpoint(self) -> None:
        selected_wells = (
            self.assignment_widget.get_selected_wells()
        )

        if not selected_wells:
            return

        try:
            setpoint = self._editor_setpoint()

            resolve_laser_setpoint(
                setpoint,
                self.plate,
                self.calibration_store,
            )

        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.warning(
                self,
                "Invalid laser assignment",
                str(exc),
            )
            return

        self.protocol.set_laser_setpoint_for_wells(
            selected_wells,
            setpoint,
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

    def _format_setpoint(
        self,
        setpoint: LaserSetpoint,
    ) -> str:
        if setpoint.mode == "current_percent":
            return f"{setpoint.value:g}%"

        requested = (
            f"{setpoint.value:g} W"
            if setpoint.mode == "power_w"
            else f"{setpoint.value:g} W/cm²"
        )

        try:
            resolved = resolve_laser_setpoint(
                setpoint,
                self.plate,
                self.calibration_store,
            )
        except (OSError, ValueError, KeyError):
            return requested + " — calibration unavailable"

        return (
            f"{requested} → {resolved.current_percent}%"
        )