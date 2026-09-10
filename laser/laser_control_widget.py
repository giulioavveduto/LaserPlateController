from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from laser.laser_modes import LaserMode


class LaserControlWidget(QGroupBox):
    mode_changed = Signal(str)
    connect_requested = Signal()
    disconnect_requested = Signal()
    current_requested = Signal(int)
    emission_requested = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__("Laser", parent)

        self.connected = False
        self.emission_enabled = False

        layout = QVBoxLayout(self)

        connection_layout = QHBoxLayout()
        connection_layout.addWidget(QLabel("Mode:"))

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(
            [
                LaserMode.SIMULATOR.value,
                LaserMode.REAL_PHOTONTEC.value,
            ]
        )
        self.mode_combo.currentTextChanged.connect(self.mode_changed.emit)
        connection_layout.addWidget(self.mode_combo)

        self.connect_button = QPushButton("Connect laser")
        self.connect_button.clicked.connect(self._request_connection)
        connection_layout.addWidget(self.connect_button)

        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self.disconnect_requested.emit)
        connection_layout.addWidget(self.disconnect_button)

        layout.addLayout(connection_layout)

        self.emission_label = QLabel("Emission command: unavailable")
        self.current_label = QLabel("Current setting: unavailable")
        layout.addWidget(self.emission_label)
        layout.addWidget(self.current_label)

        current_layout = QGridLayout()
        current_layout.addWidget(QLabel("Current:"), 0, 0)

        self.current_spinbox = QSpinBox()
        self.current_spinbox.setRange(0, 100)
        self.current_spinbox.setSuffix(" %")
        current_layout.addWidget(self.current_spinbox, 0, 1)

        self.apply_current_button = QPushButton("Apply current")
        self.apply_current_button.clicked.connect(
            lambda: self.current_requested.emit(self.current_spinbox.value())
        )
        current_layout.addWidget(self.apply_current_button, 0, 2)

        layout.addLayout(current_layout)

        emission_layout = QHBoxLayout()

        self.enable_button = QPushButton("ENABLE EMISSION")
        self.enable_button.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                background-color: #e5a000;
                color: #1f1f1f;
                padding: 6px;
            }
            QPushButton:disabled {
                background-color: #d8d8d8;
                color: #888888;
            }
            """)
        self.enable_button.clicked.connect(self._confirm_enable_emission)
        emission_layout.addWidget(self.enable_button)

        self.disable_button = QPushButton("DISABLE EMISSION")
        self.disable_button.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                background-color: #b3261e;
                color: white;
                padding: 6px;
            }
            QPushButton:disabled {
                background-color: #d8d8d8;
                color: #888888;
            }
            """)
        self.disable_button.clicked.connect(lambda: self.emission_requested.emit(False))
        emission_layout.addWidget(self.disable_button)

        layout.addLayout(emission_layout)

        interlock_label = QLabel(
            "Safety key/interlock status is not available through RS-232."
        )
        interlock_label.setWordWrap(True)
        interlock_label.setStyleSheet("color: #6b5b00;")
        layout.addWidget(interlock_label)

        self.set_connected(False)

    def _request_connection(self) -> None:
        self.mode_changed.emit(self.mode_combo.currentText())
        self.connect_requested.emit()

    def _confirm_enable_emission(self) -> None:
        answer = QMessageBox.question(
            self,
            "Enable laser emission",
            (
                "Confirm that the beam path is enclosed, the sample or "
                "power meter is correctly positioned, and all required "
                "laser-safety measures are active.\n\n"
                "Enable emission?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )

        if answer == QMessageBox.StandardButton.Yes:
            self.emission_requested.emit(True)

    def set_connected(self, connected: bool) -> None:
        self.connected = connected

        self.mode_combo.setEnabled(not connected)
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)

        if not connected:
            self.emission_enabled = False
            self.emission_label.setText("Emission command: unavailable")
            self.current_label.setText("Current setting: unavailable")

        self._update_control_states()

    def update_status(
        self,
        emission_enabled: bool,
        current_percent: int,
    ) -> None:
        self.emission_enabled = emission_enabled

        if emission_enabled:
            self.emission_label.setText("Emission command: ON")
            self.emission_label.setStyleSheet("font-weight: bold; color: #a12626;")
        else:
            self.emission_label.setText("Emission command: OFF")
            self.emission_label.setStyleSheet("font-weight: bold; color: #16803a;")

        self.current_label.setText(f"Current setting: {current_percent}%")
        if not self.current_spinbox.hasFocus():
            self.current_spinbox.setValue(current_percent)

        self._update_control_states()

    def _update_control_states(self) -> None:
        can_change_current = self.connected and not self.emission_enabled

        self.current_spinbox.setEnabled(can_change_current)
        self.apply_current_button.setEnabled(can_change_current)

        self.enable_button.setEnabled(self.connected and not self.emission_enabled)
        self.disable_button.setEnabled(self.connected and self.emission_enabled)
