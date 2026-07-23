from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QMetaObject, QThread, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
    QDialog,
    QDialogButtonBox,
    QFileDialog,     
)

from stage.stage_worker import StageWorker
from plates.plate_geometry import PlateGeometry
from plates.well_plate_widget import WellPlateWidget
from calibration.calibration_manager import CalibrationManager
from experiment.experiment_protocol import ExperimentProtocol
from experiment.experiment_designer_widget import ExperimentDesignerWidget
from experiment.protocol_io import save_protocol
from experiment.protocol_io import load_protocol, save_protocol

class MainWindow(QMainWindow):
    request_connect_stage = Signal()
    request_stage_mode = Signal(str)
    request_disconnect_stage = Signal()
    request_position = Signal()
    request_move_stage = Signal(float, float)
    request_home_stage = Signal()
    request_absolute_move = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()

        self.stage_connected = False
        self.stage_busy = False
        self.current_x_mm: float | None = None
        self.current_y_mm: float | None = None

        self.calibration_manager = CalibrationManager()
        self.experiment_protocol = ExperimentProtocol(
            plate_type="96-well plate"
        )
        self.current_protocol_path: Path | None = None
        self.setWindowTitle("Laser Plate Controller")
        self.resize(1100, 750)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        title = QLabel("Laser Plate Controller")
        title.setStyleSheet("font-size: 26px; font-weight: bold; padding: 10px;")
        main_layout.addWidget(title)

        main_layout.addWidget(self.create_device_status_section())

        body_layout = QHBoxLayout()
        body_layout.addWidget(self.create_stage_section(), stretch=1)
        body_layout.addWidget(self.create_plate_section(), stretch=2)
        main_layout.addLayout(body_layout)
        self.experiment_designer = ExperimentDesignerWidget(
            self.experiment_protocol
        )
        main_layout.addWidget(self.experiment_designer)

        main_layout.addWidget(self.create_future_devices_section())

        self.start_button = QPushButton("START EXPERIMENT")
        self.start_button.setEnabled(False)
        self.start_button.setMinimumHeight(55)
        self.start_button.setStyleSheet("font-size: 18px; font-weight: bold;")
        main_layout.addWidget(self.start_button)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Application ready")

        self.set_device_status(
            self.stage_status_label,
            "Stage: disconnected",
            False,
        )
        self.set_device_status(
            self.laser_status_label,
            "Laser: not configured",
            False,
        )
        self.set_device_status(
            self.incubator_status_label,
            "Incubator: not configured",
            False,
        )
        self.create_menu_bar()

        self.create_stage_thread()
        

    def create_menu_bar(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        self.open_action = QAction("Open...", self)
        self.save_action = QAction("Save", self)
        self.save_as_action = QAction("Save As...", self)

        self.open_action.triggered.connect(self.on_open_requested)
        self.save_action.triggered.connect(self.on_save_requested)
        self.save_as_action.triggered.connect(
            self.on_save_as_requested
        )
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_as_action.setShortcut(
            QKeySequence.StandardKey.SaveAs
        )

        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)

    def on_save_requested(self) -> None:
        if self.current_protocol_path is None:
            self.on_save_as_requested()
            return

        try:
            save_protocol(
                self.experiment_protocol,
                self.current_protocol_path,
            )
        except (OSError, TypeError, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Protocol save error",
                str(exc),
            )
            return

        self.statusBar().showMessage(
            f"Protocol saved: {self.current_protocol_path.name}",
            5000,
        )

    def on_save_as_requested(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save protocol",
            "",
            "Laser Plate Protocol (*.lpp)",
        )

        if not file_path:
            return

        path = Path(file_path)

        if path.suffix.lower() != ".lpp":
            path = path.with_suffix(".lpp")

        try:
            save_protocol(
                self.experiment_protocol,
                path,
            )
        except (OSError, TypeError, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Protocol save error",
                str(exc),
            )
            return

        self.current_protocol_path = path
        self.update_window_title()

        self.statusBar().showMessage(
            f"Protocol saved: {path.name}",
            5000,
        )

    def on_open_requested(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open protocol",
            "",
            "Laser Plate Protocol (*.lpp)",
        )

        if not file_path:
            return

        path = Path(file_path)

        try:
            loaded_protocol = load_protocol(path)
        except (OSError, TypeError, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Protocol loading error",
                str(exc),
            )
            return

        if loaded_protocol.plate_type not in [
            self.plate_combo.itemText(index)
            for index in range(self.plate_combo.count())
        ]:
            QMessageBox.critical(
                self,
                "Unknown plate type",
                (
                    "The protocol uses an unsupported plate type:\n"
                    f"{loaded_protocol.plate_type}"
                ),
            )
            return

        self.experiment_protocol.name = loaded_protocol.name
        self.experiment_protocol.plate_type = loaded_protocol.plate_type
        self.experiment_protocol.selected_wells = list(
            loaded_protocol.selected_wells
        )
        self.experiment_protocol.common_exposure_time_s = (
            loaded_protocol.common_exposure_time_s
        )

        self.plate_combo.setCurrentText(
            loaded_protocol.plate_type
        )

        if self.current_plate_widget is not None:
            self.current_plate_widget.set_selected_wells(
                loaded_protocol.selected_wells
            )

        self.experiment_designer.exposure_time_spinbox.setValue(
            loaded_protocol.common_exposure_time_s
        )
        self.experiment_designer.refresh()

        self.current_protocol_path = path
        self.update_window_title()

        self.statusBar().showMessage(
            f"Protocol opened: {path.name}",
            5000,
        )

    def create_stage_thread(self) -> None:
        self.stage_thread = QThread(self)
        self.stage_worker = StageWorker()
        self.stage_worker.moveToThread(self.stage_thread)

        self.stage_thread.started.connect(self.stage_worker.initialize)

        self.request_stage_mode.connect(self.stage_worker.set_stage_mode)
        self.request_connect_stage.connect(self.stage_worker.connect_stage)
        self.request_disconnect_stage.connect(self.stage_worker.disconnect_stage)
        self.request_position.connect(self.stage_worker.read_position)
        self.request_move_stage.connect(self.stage_worker.move_relative)
        self.request_home_stage.connect(self.stage_worker.home_stage)

        self.stage_worker.connected.connect(self.on_stage_connected)
        self.stage_worker.disconnected.connect(self.on_stage_disconnected)
        self.stage_worker.position_updated.connect(self.update_position_display)

        self.stage_worker.movement_started.connect(self.on_movement_started)
        self.stage_worker.movement_finished.connect(self.on_movement_finished)

        self.stage_worker.homing_started.connect(self.on_homing_started)
        self.stage_worker.homing_finished.connect(self.on_homing_finished)

        self.request_absolute_move.connect(self.stage_worker.move_absolute)
        self.stage_worker.absolute_movement_started.connect(
            self.on_absolute_movement_started
        )
        self.stage_worker.error_occurred.connect(self.show_stage_error)

        self.stage_thread.start()

    def create_device_status_section(self) -> QGroupBox:
        group = QGroupBox("Device status")
        layout = QHBoxLayout(group)

        self.stage_status_label = QLabel()
        self.laser_status_label = QLabel()
        self.incubator_status_label = QLabel()

        layout.addWidget(self.stage_status_label)
        layout.addWidget(self.laser_status_label)
        layout.addWidget(self.incubator_status_label)
        layout.addStretch()

        layout.addWidget(QLabel("Stage mode:"))

        self.stage_mode_combo = QComboBox()
        self.stage_mode_combo.addItems(
            [
                "Simulator",
                "Real DMSTC",
            ]
        )
        self.stage_mode_combo.setCurrentText("Simulator")
        self.stage_mode_combo.currentTextChanged.connect(
            self.request_stage_mode.emit
        )
        layout.addWidget(self.stage_mode_combo)

        self.connect_button = QPushButton("Connect stage")
        self.connect_button.clicked.connect(
            self.request_connect_stage.emit
        )
        layout.addWidget(self.connect_button)

        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setEnabled(False)
        self.disconnect_button.clicked.connect(
            self.request_disconnect_stage.emit
        )
        layout.addWidget(self.disconnect_button)

        return group

    def create_stage_section(self) -> QGroupBox:
        group = QGroupBox("Stage control")
        layout = QVBoxLayout(group)

        self.position_label = QLabel("Position\nX: undefined\nY: undefined")
        self.position_label.setStyleSheet("font-size: 18px; padding: 10px;")
        layout.addWidget(self.position_label)

        step_layout = QHBoxLayout()
        step_layout.addWidget(QLabel("Movement step:"))

        self.step_spinbox = QDoubleSpinBox()
        self.step_spinbox.setRange(0.001, 100.0)
        self.step_spinbox.setDecimals(3)
        self.step_spinbox.setValue(1.0)
        self.step_spinbox.setSuffix(" mm")
        step_layout.addWidget(self.step_spinbox)

        layout.addLayout(step_layout)

        movement_layout = QGridLayout()

        self.up_button = QPushButton("↑  +Y")
        self.left_button = QPushButton("←  −X")
        self.right_button = QPushButton("+X  →")
        self.down_button = QPushButton("↓  −Y")

        self.up_button.clicked.connect(
            lambda: self.request_movement(
                0.0,
                self.step_spinbox.value(),
            )
        )
        self.down_button.clicked.connect(
            lambda: self.request_movement(
                0.0,
                -self.step_spinbox.value(),
            )
        )
        self.left_button.clicked.connect(
            lambda: self.request_movement(
                -self.step_spinbox.value(),
                0.0,
            )
        )
        self.right_button.clicked.connect(
            lambda: self.request_movement(
                self.step_spinbox.value(),
                0.0,
            )
        )

        movement_layout.addWidget(self.up_button, 0, 1)
        movement_layout.addWidget(self.left_button, 1, 0)
        movement_layout.addWidget(self.right_button, 1, 2)
        movement_layout.addWidget(self.down_button, 2, 1)

        layout.addLayout(movement_layout)

        absolute_group = QGroupBox("Absolute position")
        absolute_layout = QGridLayout(absolute_group)

        absolute_layout.addWidget(QLabel("X:"), 0, 0)

        self.absolute_x_spinbox = QDoubleSpinBox()
        self.absolute_x_spinbox.setRange(0.0, 200.0)
        self.absolute_x_spinbox.setDecimals(3)
        self.absolute_x_spinbox.setSuffix(" mm")
        absolute_layout.addWidget(self.absolute_x_spinbox, 0, 1)

        absolute_layout.addWidget(QLabel("Y:"), 1, 0)

        self.absolute_y_spinbox = QDoubleSpinBox()
        self.absolute_y_spinbox.setRange(0.0, 200.0)
        self.absolute_y_spinbox.setDecimals(3)
        self.absolute_y_spinbox.setSuffix(" mm")
        absolute_layout.addWidget(self.absolute_y_spinbox, 1, 1)

        self.absolute_go_button = QPushButton("GO TO POSITION")
        self.absolute_go_button.clicked.connect(self.request_absolute_position)
        absolute_layout.addWidget(
            self.absolute_go_button,
            2,
            0,
            1,
            2,
        )

        layout.addWidget(absolute_group)

        self.home_button = QPushButton("Home stage")
        self.home_button.clicked.connect(self.confirm_home_stage)
        layout.addWidget(self.home_button)

        self.set_stage_controls_enabled(False)

        return group


    def update_window_title(self) -> None:
        if self.current_protocol_path is None:
            protocol_name = "Untitled"
        else:
            protocol_name = self.current_protocol_path.name

        self.setWindowTitle(
            f"Laser Plate Controller — {protocol_name}"
        )

    def create_plate_section(self) -> QGroupBox:
        group = QGroupBox("Plate configuration")
        layout = QVBoxLayout(group)

        plate_type_layout = QHBoxLayout()
        plate_type_layout.addWidget(QLabel("Plate type:"))

        

        self.plate_combo = QComboBox()
        self.plate_combo.addItems(
            [
                "96-well plate",
                "48-well plate",
                "24-well plate",
                "12-well plate",
                "6-well plate",
                "Add new plate…",
            ]
        )
        self.plate_combo.currentTextChanged.connect(self.change_plate_type)

        plate_type_layout.addWidget(self.plate_combo)
        layout.addLayout(plate_type_layout)

        self.plate_map_container = QWidget()
        self.plate_map_layout = QVBoxLayout(self.plate_map_container)
        self.plate_map_layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self.plate_map_container)

        self.calibration_status_label = QLabel("A1 calibration: not defined")
        layout.addWidget(self.calibration_status_label)

        self.calibrate_button = QPushButton("Calibrate current position as A1")
        self.calibrate_button.setEnabled(False)
        self.calibrate_button.clicked.connect(self.open_a1_calibration_dialog)
        layout.addWidget(self.calibrate_button)
        self.navigate_to_well_button = QPushButton(
            "Navigate to selected well"
        )
        self.navigate_to_well_button.setEnabled(False)
        layout.addWidget(self.navigate_to_well_button)

        self.navigate_to_well_button.clicked.connect(
            self.navigate_to_selected_well
        )

        self.current_plate_widget = None
        self.load_plate_widget("96-well plate")

        return group

    def navigate_to_selected_well(self) -> None:
        if (
            self.current_plate_widget is None
            or not self.stage_connected
            or self.stage_busy
        ):
            return

        selected_wells = (
            self.current_plate_widget.get_selected_wells()
        )

        if len(selected_wells) != 1:
            return

        well_name = selected_wells[0]
        plate = self.current_plate_widget.plate

        try:
            relative_x_mm, relative_y_mm = (
                plate.get_relative_position(well_name)
            )

            absolute_x_mm, absolute_y_mm = (
                self.calibration_manager.get_absolute_well_position(
                    plate.name,
                    relative_x_mm,
                    relative_y_mm,
                )
            )
        except (ValueError, RuntimeError) as exc:
            QMessageBox.critical(
                self,
                "Navigation error",
                str(exc),
            )
            return

        self.request_absolute_move.emit(
            absolute_x_mm,
            absolute_y_mm,
        )

    def update_navigation_button_state(self) -> None:
        if self.current_plate_widget is None:
            self.navigate_to_well_button.setEnabled(False)
            return

        selected_wells = (
            self.current_plate_widget.get_selected_wells()
        )
        plate_name = self.current_plate_widget.plate.name

        can_navigate = (
            self.stage_connected
            and not self.stage_busy
            and len(selected_wells) == 1
            and self.calibration_manager.is_calibrated(plate_name)
        )

        self.navigate_to_well_button.setEnabled(can_navigate)

    def clear_plate_widget(self) -> None:
        while self.plate_map_layout.count():
            item = self.plate_map_layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        self.current_plate_widget = None

    def load_plate_widget(self, plate_name: str) -> None:
        if plate_name == "Add new plate…":
            return

        try:
            plate = PlateGeometry(plate_name)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Plate loading error",
                str(exc),
            )
            return

        self.clear_plate_widget()

        self.current_plate_widget = WellPlateWidget(plate)
        self.experiment_protocol.plate_type = plate.name
        self.experiment_protocol.selected_wells = []

        self.current_plate_widget.selection_changed.connect(
            self.on_well_selection_changed
        )

        self.plate_map_layout.addWidget(self.current_plate_widget)


        if hasattr(self, "experiment_designer"):
            self.experiment_designer.refresh()

        self.update_calibration_status()
        self.update_navigation_button_state()

        self.statusBar().showMessage(f"Loaded {plate_name}")

    def change_plate_type(self, plate_name: str) -> None:
        if plate_name == "Add new plate…":
            previous_plate_name = (
                self.current_plate_widget.plate.name
                if self.current_plate_widget is not None
                else "96-well plate"
            )

            QMessageBox.information(
                self,
                "Add plate",
                "The custom plate editor will be added in a later version.",
            )

            self.plate_combo.blockSignals(True)
            self.plate_combo.setCurrentText(previous_plate_name)
            self.plate_combo.blockSignals(False)

            return

        self.load_plate_widget(plate_name)

    def on_well_selection_changed(
        self,
        selected_wells: list[str],
    ) -> None:
        self.experiment_protocol.selected_wells = list(selected_wells)
        self.experiment_designer.refresh()
        self.update_navigation_button_state()

        self.statusBar().showMessage(
            f"{self.experiment_protocol.selected_well_count} well(s) selected"
        )

    def update_calibration_status(self) -> None:
        if self.current_plate_widget is None:
            self.calibration_status_label.setText(
                "A1 calibration: not defined"
            )
            return

        plate_name = self.current_plate_widget.plate.name
        a1_position = self.calibration_manager.get_a1(plate_name)

        if a1_position is None:
            self.calibration_status_label.setText(
                "A1 calibration: not defined"
            )
            self.calibration_status_label.setStyleSheet(
                "font-weight: bold; color: #a12626;"
            )
            return

        a1_x_mm, a1_y_mm = a1_position

        self.calibration_status_label.setText(
            f"A1 calibration: X={a1_x_mm:.3f} mm, "
            f"Y={a1_y_mm:.3f} mm"
        )
        self.calibration_status_label.setStyleSheet(
            "font-weight: bold; color: #16803a;"
        )
        self.update_navigation_button_state()

    def open_a1_calibration_dialog(self) -> None:
        if not self.stage_connected:
            QMessageBox.warning(
                self,
                "Stage not connected",
                "Connect the stage or simulator before calibrating A1.",
            )
            return

        if self.current_plate_widget is None:
            QMessageBox.warning(
                self,
                "No plate selected",
                "Select a plate before calibrating A1.",
            )
            return

        if self.current_x_mm is None or self.current_y_mm is None:
            QMessageBox.warning(
                self,
                "Position unavailable",
                "The current stage position is unavailable.",
            )
            return

        plate_name = self.current_plate_widget.plate.name

        dialog = QDialog(self)
        dialog.setWindowTitle("A1 calibration")
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        instruction_label = QLabel(
            "Confirm that the laser fibre is centred over well A1.\n\n"
            f"Plate: {plate_name}\n"
            f"Current X: {self.current_x_mm:.3f} mm\n"
            f"Current Y: {self.current_y_mm:.3f} mm\n\n"
            "Store this position as A1?"
        )
        layout.addWidget(instruction_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self.calibration_manager.set_a1(
                plate_name,
                self.current_x_mm,
                self.current_y_mm,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Calibration error",
                str(exc),
            )
            return

        self.update_calibration_status()

        QMessageBox.information(
            self,
            "Calibration saved",
            f"A1 calibration saved for {plate_name}.",
        )

    def create_future_devices_section(self) -> QGroupBox:
        group = QGroupBox("Laser and incubator — future modules")
        layout = QHBoxLayout(group)

        laser_box = QGroupBox("Laser")
        laser_layout = QVBoxLayout(laser_box)
        laser_layout.addWidget(QLabel("Emission control: unavailable"))
        laser_layout.addWidget(QLabel("Power control: unavailable"))
        laser_layout.addWidget(QLabel("Preheat: unavailable"))

        incubator_box = QGroupBox("Incubator")
        incubator_layout = QVBoxLayout(incubator_box)
        incubator_layout.addWidget(QLabel("Temperature: unavailable"))
        incubator_layout.addWidget(QLabel("Humidity: unavailable"))
        incubator_layout.addWidget(QLabel("CO₂: unavailable"))

        layout.addWidget(laser_box)
        layout.addWidget(incubator_box)

        return group

    def set_device_status(
        self,
        label: QLabel,
        text: str,
        connected: bool,
    ) -> None:
        colour = "#16803a" if connected else "#a12626"
        symbol = "●" if connected else "○"

        label.setText(f"{symbol} {text}")
        label.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {colour};")

    def set_stage_controls_enabled(self, enabled: bool) -> None:
        controls = (
            self.up_button,
            self.down_button,
            self.left_button,
            self.right_button,
            self.home_button,
            self.step_spinbox,
            self.absolute_x_spinbox,
            self.absolute_y_spinbox,
            self.absolute_go_button,
        )

        for control in controls:
            control.setEnabled(enabled)

    def request_movement(
        self,
        dx_mm: float,
        dy_mm: float,
    ) -> None:
        if not self.stage_connected or self.stage_busy:
            return

        self.request_move_stage.emit(dx_mm, dy_mm)

    def confirm_home_stage(self) -> None:
        if not self.stage_connected or self.stage_busy:
            return

        answer = QMessageBox.warning(
            self,
            "Confirm stage homing",
            "The stage will move to its reference corner.\n\n"
            "Ensure the complete travel path is clear before continuing.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )

        if answer == QMessageBox.StandardButton.Ok:
            self.request_home_stage.emit()

    def on_stage_connected(
        self,
        x_mm: float,
        y_mm: float,
    ) -> None:
        self.stage_connected = True
        self.stage_busy = False

        mode = self.stage_mode_combo.currentText()

        self.set_device_status(
            self.stage_status_label,
            f"Stage: {mode} connected",
            True,
        )

        self.connect_button.setEnabled(False)
        self.stage_mode_combo.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self.set_stage_controls_enabled(True)
        self.calibrate_button.setEnabled(True)

        self.update_position_display(x_mm, y_mm)
        if mode == "Simulator":
            self.statusBar().showMessage(
                "Simulated stage connected — no physical hardware is active"
            )
        else:
            self.statusBar().showMessage(
                "Real DMSTC stage connected"
            )

        self.update_navigation_button_state()

    def on_stage_disconnected(self) -> None:
        self.stage_connected = False
        self.stage_busy = False

        self.set_device_status(
            self.stage_status_label,
            "Stage: disconnected",
            False,
        )

        self.connect_button.setEnabled(True)
        self.stage_mode_combo.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.set_stage_controls_enabled(False)
        self.calibrate_button.setEnabled(False)

        self.position_label.setText("Position\nX: undefined\nY: undefined")
        self.statusBar().showMessage("Stage disconnected")
        self.update_navigation_button_state()

    def update_position_display(
        self,
        x_mm: float,
        y_mm: float,
    ) -> None:
        self.current_x_mm = x_mm
        self.current_y_mm = y_mm

        self.position_label.setText(
            f"Position\nX: {x_mm:.3f} mm\nY: {y_mm:.3f} mm"
        )

    def on_movement_started(
        self,
        dx_mm: float,
        dy_mm: float,
    ) -> None:
        self.stage_busy = True
        self.set_stage_controls_enabled(False)

        self.statusBar().showMessage(
            f"Moving stage: ΔX={dx_mm:.3f} mm, " f"ΔY={dy_mm:.3f} mm"
        )
        self.update_navigation_button_state()

    def on_movement_finished(
        self,
        x_mm: float,
        y_mm: float,
    ) -> None:
        self.stage_busy = False
        self.set_stage_controls_enabled(True)

        self.update_position_display(x_mm, y_mm)
        self.statusBar().showMessage("Movement complete")
        self.update_navigation_button_state()

    def on_homing_started(self) -> None:
        self.stage_busy = True
        self.set_stage_controls_enabled(False)
        self.statusBar().showMessage("Homing stage...")
        self.update_navigation_button_state()

    def on_homing_finished(
        self,
        x_mm: float,
        y_mm: float,
    ) -> None:
        self.stage_busy = False
        self.set_stage_controls_enabled(True)

        self.update_position_display(x_mm, y_mm)
        self.statusBar().showMessage("Homing complete")
        self.update_navigation_button_state()

    def show_stage_error(self, message: str) -> None:
        self.stage_busy = False

        if self.stage_connected:
            self.set_stage_controls_enabled(True)

        QMessageBox.critical(
            self,
            "Stage error",
            message,
        )
        self.update_navigation_button_state()
    
    def request_absolute_position(self) -> None:
        if not self.stage_connected or self.stage_busy:
            return

        x_mm = self.absolute_x_spinbox.value()
        y_mm = self.absolute_y_spinbox.value()

        self.request_absolute_move.emit(x_mm, y_mm)

    def on_absolute_movement_started(
        self,
        x_mm: float,
        y_mm: float,
    ) -> None:
        self.stage_busy = True
        self.set_stage_controls_enabled(False)

        self.statusBar().showMessage(
            f"Moving to absolute position: " f"X={x_mm:.3f} mm, Y={y_mm:.3f} mm"
        )
        self.update_navigation_button_state()

    def closeEvent(self, event) -> None:
        if self.stage_thread.isRunning():
            QMetaObject.invokeMethod(
                self.stage_worker,
                "disconnect_stage",
                Qt.ConnectionType.BlockingQueuedConnection,
            )

            QMetaObject.invokeMethod(
                self.stage_worker,
                "deleteLater",
                Qt.ConnectionType.QueuedConnection,
            )

            self.stage_thread.quit()
            self.stage_thread.wait()

        event.accept()


def main() -> None:
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
