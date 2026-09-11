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
            elif setpoint.mode != "current_percent":
                problems.append(
                    f"{well}: power calibration is not implemented; use current %."
                )
            elif not float(setpoint.value).is_integer():
                problems.append(f"{well}: current must be an integer percentage.")
        if not window.laser_connected:
            problems.append("Connect the laser or laser simulator.")
        problems.append(
            "Automatic laser execution is not implemented in this checkpoint. "
            "Irradiation cannot be launched yet."
        )
    return problems


class StartExperimentDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.snapshot = None
        self.run_directory = None
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
        self.buttons.accepted.connect(self.confirm_start)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.mode.currentIndexChanged.connect(self.refresh)
        self.name.textChanged.connect(self.refresh)
        self.key_off.toggled.connect(self.refresh)
        self.refresh()

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Run output folder", self.folder.text()
        )
        if folder:
            self.folder.setText(folder)

    def refresh(self):
        stage_only = bool(self.mode.currentData())
        self.key_off.setVisible(stage_only)
        problems = launch_problems(self.window, stage_only)
        if not self.name.text().strip():
            problems.append("Enter a protocol name.")
        if stage_only and not self.key_off.isChecked():
            problems.append("Confirm that the physical laser is OFF.")
        protocol = self.window.experiment_protocol
        self.summary.setText(
            f"{len(protocol.selected_wells)} wells · Stage: {self.window.stage_mode_combo.currentText()}\n"
            "Stage-only countdowns are not irradiation measurements."
        )
        self.problems.setPlainText(
            "\n".join(problems)
            if problems
            else "Protocol valid for a stage-only test. Start the test?"
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Yes).setEnabled(
            not problems
        )

    def confirm_start(self):
        # Recheck after the modal review, since device status may have changed.
        self.refresh()
        if not self.buttons.button(QDialogButtonBox.StandardButton.Yes).isEnabled():
            return
        snapshot = deepcopy(self.window.experiment_protocol)
        snapshot.name = self.name.text().strip()
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
                "mode": "stage_only",
                "stage_mode": self.window.stage_mode_combo.currentText(),
                "a1_mm": self.window.calibration_manager.get_a1(snapshot.plate_type),
                "note": "No irradiation; stage movements and countdowns only.",
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
