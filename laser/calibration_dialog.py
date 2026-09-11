from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from laser.power_calibration import (
    CalibrationPoint,
    LaserCalibrationStore,
    LaserPowerCalibration,
)


class FocusWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class LaserCalibrationDialog(QDialog):
    CURRENT_LEVELS = tuple(range(0, 101, 5))

    def __init__(
        self,
        store: LaserCalibrationStore,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.store = store
        self.active_calibration = store.get_active()
        self.saved_calibration: LaserPowerCalibration | None = None

        self.checkboxes: dict[int, QCheckBox] = {}
        self.power_spinboxes: dict[int, QDoubleSpinBox] = {}

        self.setWindowTitle("Laser power calibration")
        self.resize(680, 720)

        layout = QVBoxLayout(self)

        explanation = QLabel(
            "Enter the optical power measured with the power meter. "
            "Only checked rows will belong to the new active calibration. "
            "The optional 0% point is fixed at 0 W. At least two points "
            "are required and power must increase strictly with current."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        self.active_label = QLabel()
        self.active_label.setWordWrap(True)
        layout.addWidget(self.active_label)

        self.table = QTableWidget(
            len(self.CURRENT_LEVELS),
            4,
        )
        self.table.setHorizontalHeaderLabels(
            [
                "Use",
                "Current (%)",
                "Previous measured power (W)",
                "New measured power (W)",
            ]
        )
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            3,
            QHeaderView.ResizeMode.Stretch,
        )

        previous_values = {}

        if self.active_calibration is not None:
            previous_values = {
                point.current_percent: point.power_w
                for point in self.active_calibration.points
            }

        for row, current_percent in enumerate(
            self.CURRENT_LEVELS
        ):
            checkbox = QCheckBox()
            checkbox_container = QWidget()
            checkbox_layout = QHBoxLayout(
                checkbox_container
            )
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_layout.setAlignment(
                Qt.AlignmentFlag.AlignCenter
            )
            checkbox_layout.addWidget(checkbox)

            current_item = QTableWidgetItem(
                str(current_percent)
            )
            current_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter
            )
            current_item.setFlags(
                current_item.flags()
                & ~Qt.ItemFlag.ItemIsEditable
            )

            previous_power = previous_values.get(
                current_percent
            )
            previous_item = QTableWidgetItem(
                "—"
                if previous_power is None
                else f"{previous_power:.4f}"
            )
            previous_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter
            )
            previous_item.setFlags(
                previous_item.flags()
                & ~Qt.ItemFlag.ItemIsEditable
            )

            power_spinbox = FocusWheelDoubleSpinBox()
            power_spinbox.setDecimals(4)
            power_spinbox.setSingleStep(0.01)
            power_spinbox.setSuffix(" W")

            if current_percent == 0:
                power_spinbox.setRange(0.0, 0.0)
                power_spinbox.setValue(0.0)
            else:
                power_spinbox.setRange(0.0, 1000.0)

            checkbox.toggled.connect(
                lambda checked,
                spinbox=power_spinbox,
                percentage=current_percent:
                spinbox.setEnabled(
                    checked and percentage != 0
                )
            )

            if previous_power is not None:
                checkbox.setChecked(True)
                power_spinbox.setValue(previous_power)
            else:
                power_spinbox.setEnabled(False)

            self.table.setCellWidget(
                row,
                0,
                checkbox_container,
            )
            self.table.setItem(row, 1, current_item)
            self.table.setItem(row, 2, previous_item)
            self.table.setCellWidget(
                row,
                3,
                power_spinbox,
            )

            self.checkboxes[current_percent] = checkbox
            self.power_spinboxes[current_percent] = (
                power_spinbox
            )

        layout.addWidget(self.table)

        preset_layout = QHBoxLayout()

        every_five_button = QPushButton("Every 5%")
        every_five_button.clicked.connect(
            lambda: self._select_levels(
                set(self.CURRENT_LEVELS)
            )
        )
        preset_layout.addWidget(every_five_button)

        every_ten_button = QPushButton("Every 10%")
        every_ten_button.clicked.connect(
            lambda: self._select_levels(
                {
                    value
                    for value in self.CURRENT_LEVELS
                    if value % 10 == 0
                }
            )
        )
        preset_layout.addWidget(every_ten_button)

        sparse_button = QPushButton(
            "0, 10, 30, 50, 70, 90%"
        )
        sparse_button.clicked.connect(
            lambda: self._select_levels(
                {10, 30, 50, 70, 90}
            )
        )
        preset_layout.addWidget(sparse_button)

        restore_button = QPushButton("Restore previous")
        restore_button.clicked.connect(
            self._restore_previous
        )
        preset_layout.addWidget(restore_button)

        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(
            lambda: self._select_levels(set())
        )
        preset_layout.addWidget(clear_button)

        layout.addLayout(preset_layout)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        save_button = buttons.button(
            QDialogButtonBox.StandardButton.Save
        )
        save_button.setText("Save as active calibration")

        self._update_active_label()

    def _update_active_label(self) -> None:
        if self.active_calibration is None:
            self.active_label.setText(
                "No active laser calibration."
            )
            self.active_label.setStyleSheet(
                "font-weight: bold; color: #a12626;"
            )
            return

        calibration = self.active_calibration
        self.active_label.setText(
            "Active calibration: "
            f"{calibration.calibration_id[:8]} — "
            f"{calibration.created_at_utc} — "
            f"{len(calibration.points)} measured points — "
            f"{calibration.minimum_power_w:g} to "
            f"{calibration.maximum_power_w:g} W"
        )
        self.active_label.setStyleSheet(
            "font-weight: bold; color: #16803a;"
        )

    def _select_levels(
        self,
        selected_levels: set[int],
    ) -> None:
        for current_percent, checkbox in (
            self.checkboxes.items()
        ):
            checkbox.setChecked(
                current_percent in selected_levels
            )

    def _restore_previous(self) -> None:
        if self.active_calibration is None:
            self._select_levels(set())
            return

        previous_values = {
            point.current_percent: point.power_w
            for point in self.active_calibration.points
        }

        self._select_levels(set(previous_values))

        for current_percent, power_w in (
            previous_values.items()
        ):
            spinbox = self.power_spinboxes.get(
                current_percent
            )
            if spinbox is not None:
                spinbox.setValue(power_w)

    def _save(self) -> None:
        selected_points: list[CalibrationPoint] = []

        try:
            for current_percent in self.CURRENT_LEVELS:
                if not self.checkboxes[
                    current_percent
                ].isChecked():
                    continue

                power_w = self.power_spinboxes[
                    current_percent
                ].value()

                selected_points.append(
                    CalibrationPoint(
                        current_percent=current_percent,
                        power_w=power_w,
                    )
                )

            calibration = LaserPowerCalibration.create(
                selected_points
            )

        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Invalid calibration",
                str(exc),
            )
            return

        answer = QMessageBox.question(
            self,
            "Replace active calibration",
            (
                f"Use these {len(calibration.points)} points as "
                "the new active laser calibration?\n\n"
                "The active point set will be replaced entirely. "
                "The previous calibration will remain stored only "
                "for traceability of earlier protocols."
            ),
            (
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.Cancel
            ),
            QMessageBox.StandardButton.Cancel,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.saved_calibration = (
                self.store.save_new(
                    calibration.points
                )
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Calibration save error",
                str(exc),
            )
            return

        self.accept()