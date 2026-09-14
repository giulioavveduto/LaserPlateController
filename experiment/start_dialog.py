"""Start review for the first workflow checkpoint (stage-only execution)."""

from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from plates.plate_geometry import PlateGeometry
from laser.setpoint_conversion import resolve_laser_setpoint
from experiment.well_ordering import order_wells


def launch_problems(window, stage_only: bool) -> list[str]:
    protocol = window.experiment_protocol
    problems = []
    if window.experiment_runner.is_running:
        problems.append("An experiment is already running.")
    if not window.stage_connected:
        problems.append("Connect the stage or stage simulator.")
    if not window.stage_homed:
        problems.append("Home the stage before starting.")
    if window.stage_busy:
        problems.append("Wait for the stage to finish moving.")
    if not protocol.selected_wells:
        problems.append("Select at least one well.")
    if len(protocol.selected_wells) != len(set(protocol.selected_wells)):
        problems.append("The protocol contains duplicate wells.")
    try:
        plate = PlateGeometry(protocol.plate_type)
        calibrated = window.calibration_manager.is_calibrated(plate.name)
        if not calibrated:
            problems.append("Set the A1 calibration for this plate.")
        for well in protocol.selected_wells:
            plate.normalize_well_name(well)
            duration = protocol.exposure_time_for(well)
            if not math.isfinite(duration) or duration <= 0:
                problems.append(f"{well}: assign a finite duration greater than zero.")
            if calibrated:
                x, y = window.calibration_manager.get_absolute_well_position(
                    plate.name, *plate.get_relative_position(well)
                )
                if not all(math.isfinite(v) and v >= 0 for v in (x, y)):
                    problems.append(f"{well}: invalid calibrated coordinates.")
                elif window.stage_mode_combo.currentText() == "Simulator" and (
                    x > 80 or y > 120
                ):
                    problems.append(f"{well}: outside the simulator travel range.")
    except (ValueError, RuntimeError, TypeError) as exc:
        problems.append(str(exc))

    if stage_only:
        if not window.developer_action.isChecked():
            problems.append("Stage-only tests require Developer mode.")
        if window.laser_connected:
            problems.append(
                "Disconnect the laser in the GUI before this stage-only test."
            )
    else:
        for well in protocol.selected_wells:
            setpoint = protocol.laser_setpoint_for(well)
            if setpoint is None:
                problems.append(f"{well}: laser assignment missing.")
            elif not math.isfinite(setpoint.value) or not setpoint.is_valid:
                problems.append(f"{well}: invalid laser assignment.")
            else:
                try:
                    resolve_laser_setpoint(
                        setpoint,
                        plate,
                        window.laser_calibration_store,
                    )
                except (OSError, ValueError, KeyError) as exc:
                    problems.append(f"{well}: {exc}")
        if not window.laser_connected:
            problems.append("Connect the laser or laser simulator.")
        stage_is_simulator = window.stage_mode_combo.currentText() == "Simulator"
        laser_is_simulator = (
            window.laser_control_widget.mode_combo.currentText() == "Simulator"
        )

        if stage_is_simulator != laser_is_simulator:
            problems.append(
                "For automatic execution, use both simulators or both "
                "real devices. Mixed real/simulator operation is blocked."
            )
    return problems


class StartExperimentDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.snapshot = None
        self.run_directory = None
        self.stage_only = True
        self.export_excel_requested = True
        self.resolved_current_percents: dict[str, int] = {}
        self.resolved_laser_setpoints: dict[
            str,
            dict[str, object],
        ] = {}
        self.used_laser_calibrations: dict[str, dict[str, object]] = {}
        self.setWindowTitle("Review experiment before starting")
        self.resize(650, 500)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItem("Irradiation experiment", False)
        if window.developer_action.isChecked():
            self.mode.addItem("Stage-only test — no irradiation", True)
        form.addRow("Execution mode:", self.mode)
        self.name = QLineEdit(window.experiment_protocol.name)
        form.addRow("Protocol name:", self.name)
        self.folder = QLineEdit(str(Path(__file__).resolve().parents[1] / "runs"))
        self.folder.setReadOnly(True)
        form.addRow("Save run under:", self.folder)
        browse = QPushButton("Choose output folder…")
        browse.clicked.connect(self.choose_folder)
        form.addRow("", browse)
        layout.addLayout(form)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        from PySide6.QtWidgets import QPlainTextEdit

        self.problems = QPlainTextEdit()
        self.problems.setReadOnly(True)
        layout.addWidget(self.problems)
        self.key_off = QCheckBox(
            "I confirm that the physical laser is switched off or its safety key is OFF."
        )
        self.irradiation_safety = QCheckBox(
            "I confirm that the enclosure is closed, the optical path is "
            "secured, and all required laser safety measures are active."
        )
        layout.addWidget(self.irradiation_safety)
        layout.addWidget(self.key_off)
        layout.addWidget(
            QLabel(
                "A timestamped protocol snapshot will be saved before movement starts."
            )
        )
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Yes).setText(
            "Yes, start test"
        )
        self.export_excel = QCheckBox(
            "Create a two-sheet Excel report when the experiment ends."
        )
        self.export_excel.setChecked(True)
        layout.addWidget(self.export_excel)
        self.buttons.accepted.connect(self.confirm_start)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.mode.currentIndexChanged.connect(self.refresh)
        self.name.textChanged.connect(self.refresh)
        self.key_off.toggled.connect(self.refresh)
        self.irradiation_safety.toggled.connect(self.refresh)
        self.refresh()

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Run output folder", self.folder.text()
        )
        if folder:
            self.folder.setText(folder)

    def refresh(self):
        stage_only = bool(self.mode.currentData())
        real_irradiation = (
            not stage_only and self.window.stage_mode_combo.currentText() != "Simulator"
        )
        self.key_off.setVisible(stage_only)
        self.irradiation_safety.setVisible(real_irradiation)
        problems = launch_problems(self.window, stage_only)
        if not self.name.text().strip():
            problems.append("Enter a protocol name.")
        if stage_only and not self.key_off.isChecked():
            problems.append("Confirm that the physical laser is OFF.")
        if real_irradiation and not self.irradiation_safety.isChecked():
            problems.append("Confirm the laser enclosure and safety conditions.")
        protocol = self.window.experiment_protocol
        self.summary.setText(
            f"{len(protocol.selected_wells)} wells · "
            f"Stage: "
            f"{self.window.stage_mode_combo.currentText()}\n"
            f"Irradiation order: "
            f"{self.window.irradiation_order_combo.currentText()}\n"
            "Stage-only countdowns are not irradiation measurements."
        )
        self.problems.setPlainText(
            "\n".join(problems)
            if problems
            else "Protocol valid for a stage-only test. Start the test?"
        )
        if problems:
            validation_text = "\n".join(problems)
        elif stage_only:
            validation_text = "Protocol valid for a stage-only test. " "Start the test?"
        else:
            validation_text = (
                "Protocol valid for automatic irradiation. "
                "All laser assignments were resolved successfully."
            )

        self.problems.setPlainText(validation_text)

        self.buttons.button(QDialogButtonBox.StandardButton.Yes).setText(
            "Yes, start stage-only test" if stage_only else "Yes, start experiment"
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Yes).setEnabled(
            not problems
        )

    def confirm_start(self):
        # Recheck after the modal review, since device status may have changed.
        self.refresh()
        if not self.buttons.button(QDialogButtonBox.StandardButton.Yes).isEnabled():
            return

        self.stage_only = bool(self.mode.currentData())
        self.export_excel_requested = self.export_excel.isChecked()
        snapshot = deepcopy(self.window.experiment_protocol)
        snapshot.name = self.name.text().strip()
        self.resolved_current_percents = {}
        self.resolved_laser_setpoints = {}
        self.used_laser_calibrations = {}
        ordering_start_position_mm = None

        try:
            plate = PlateGeometry(snapshot.plate_type)
            positions_mm = None

            if snapshot.irradiation_order == "optimized":
                current_x = self.window.current_x_mm
                current_y = self.window.current_y_mm

                if current_x is None or current_y is None:
                    raise ValueError("The current stage position is unavailable.")

                ordering_start_position_mm = (
                    current_x,
                    current_y,
                )

                positions_mm = {}

                for well in snapshot.selected_wells:
                    relative_position = plate.get_relative_position(well)
                    positions_mm[well] = (
                        self.window.calibration_manager.get_absolute_well_position(
                            plate.name,
                            *relative_position,
                        )
                    )

            snapshot.selected_wells = order_wells(
                snapshot.selected_wells,
                plate,
                snapshot.irradiation_order,
                positions_mm=positions_mm,
                start_position_mm=(
                    ordering_start_position_mm
                    if ordering_start_position_mm is not None
                    else (0.0, 0.0)
                ),
            )

        except (ValueError, RuntimeError, KeyError) as exc:
            QMessageBox.critical(
                self,
                "Irradiation ordering error",
                ("The experiment was not started.\n\n" f"{exc}"),
            )
            return

        if not self.stage_only:
            try:

                for well in snapshot.selected_wells:
                    setpoint = snapshot.laser_setpoint_for(well)

                    if setpoint is None:
                        raise ValueError(f"{well}: laser assignment missing.")

                    resolved = resolve_laser_setpoint(
                        setpoint,
                        plate,
                        self.window.laser_calibration_store,
                    )

                    self.resolved_current_percents[well] = resolved.current_percent

                    self.resolved_laser_setpoints[well] = {
                        "requested_mode": resolved.requested_mode,
                        "requested_value": resolved.requested_value,
                        "calibration_id": resolved.calibration_id,
                        "current_percent": resolved.current_percent,
                        "estimated_power_w": resolved.achieved_power_w,
                        "estimated_irradiance_w_cm2": (
                            resolved.achieved_irradiance_w_cm2
                        ),
                    }

                    if resolved.calibration_id is not None:
                        calibration = (
                            self.window.laser_calibration_store.get_calibration(
                                resolved.calibration_id
                            )
                        )
                        self.used_laser_calibrations[resolved.calibration_id] = (
                            calibration.to_dict()
                        )

            except (OSError, ValueError, KeyError) as exc:
                QMessageBox.critical(
                    self,
                    "Laser assignment error",
                    ("The experiment was not started.\n\n" f"{exc}"),
                )
                return
        stamp = datetime.now().astimezone()
        slug = (
            re.sub(r"[^A-Za-z0-9_-]+", "_", snapshot.name).strip("_")[:60]
            or "experiment"
        )
        run_id = f"{stamp:%Y%m%d_%H%M%S}_{slug}_{uuid4().hex[:8]}"
        directory = Path(self.folder.text()) / run_id
        try:
            directory.mkdir(parents=True, exist_ok=False)
            # One file is the authoritative snapshot plus start metadata.
            data = snapshot.to_dict()
            data["run"] = {
                "id": run_id,
                "created_at": stamp.isoformat(),
                "mode": ("stage_only" if self.stage_only else "automatic_irradiation"),
                "stage_mode": self.window.stage_mode_combo.currentText(),
                "laser_mode": (
                    "Not applicable"
                    if self.stage_only
                    else (self.window.laser_control_widget.mode_combo.currentText())
                ),
                "a1_mm": self.window.calibration_manager.get_a1(snapshot.plate_type),
                "irradiation_order": snapshot.irradiation_order,
                "resolved_well_sequence": list(snapshot.selected_wells),
                "ordering_start_position_mm": (
                    None
                    if ordering_start_position_mm is None
                    else list(ordering_start_position_mm)
                ),
                "note": (
                    "No irradiation; stage movements and countdowns only."
                    if self.stage_only
                    else (
                        "Automatic laser sequence; exposure means "
                        "controller-confirmed emission."
                    )
                ),
                "excel_report_requested": self.export_excel_requested,
                "resolved_current_percent_by_well": dict(
                    self.resolved_current_percents
                ),
                "resolved_laser_setpoints_by_well": dict(self.resolved_laser_setpoints),
                "laser_calibrations": dict(self.used_laser_calibrations),
            }
            with (directory / "protocol.lpp").open("x", encoding="utf-8") as file:
                json.dump(data, file, indent=4, allow_nan=False)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.critical(
                self, "Run could not be saved", f"Nothing was started.\n{exc}"
            )
            return
        self.snapshot = snapshot
        self.run_directory = directory
        self.accept()
