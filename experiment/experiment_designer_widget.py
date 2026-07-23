from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from experiment.experiment_protocol import ExperimentProtocol

class ExperimentDesignerWidget(QWidget):
    protocol_changed = Signal()

    def __init__(
        self,
        protocol: ExperimentProtocol,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.protocol = protocol

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("Experiment Designer")
        form_layout = QFormLayout(group)

        self.exposure_time_spinbox = QDoubleSpinBox()
        self.exposure_time_spinbox.setRange(0.0, 3600.0)
        self.exposure_time_spinbox.setDecimals(1)
        self.exposure_time_spinbox.setSingleStep(1.0)
        self.exposure_time_spinbox.setSuffix(" s")
        self.exposure_time_spinbox.setValue(
            self.protocol.common_exposure_time_s
        )
        self.exposure_time_spinbox.valueChanged.connect(
            self.on_exposure_time_changed
        )

        self.selected_wells_label = QLabel()
        self.estimated_duration_label = QLabel()
        self.validity_label = QLabel()
        self.experiment_state_label = QLabel("Idle")
        self.current_well_label = QLabel("--")
        self.remaining_time_label = QLabel("--")

        form_layout.addRow(
            "Common exposure time:",
            self.exposure_time_spinbox,
        )
        form_layout.addRow(
            "Selected wells:",
            self.selected_wells_label,
        )
        form_layout.addRow(
            "Estimated duration:",
            self.estimated_duration_label,
        )
        form_layout.addRow(
            "Protocol status:",
            self.validity_label,
        )
        form_layout.addRow(
            "Experiment state:",
            self.experiment_state_label,
        )
        form_layout.addRow(
            "Current well:",
            self.current_well_label,
        )
        form_layout.addRow(
            "Remaining time:",
            self.remaining_time_label,
        )

        main_layout.addWidget(group)

        self.refresh()

    def on_exposure_time_changed(self, value: float) -> None:
        self.protocol.common_exposure_time_s = value
        self.refresh()
        self.protocol_changed.emit()

    def refresh(self) -> None:
        self.selected_wells_label.setText(
            str(self.protocol.selected_well_count)
        )

        self.estimated_duration_label.setText(
            self.format_duration(
                self.protocol.estimated_duration_s
            )
        )

        if self.protocol.is_valid:
            self.validity_label.setText("Valid")
            self.validity_label.setStyleSheet(
                "font-weight: bold; color: #16803a;"
            )
        else:
            self.validity_label.setText("Incomplete")
            self.validity_label.setStyleSheet(
                "font-weight: bold; color: #a12626;"
            )

    @staticmethod
    def format_duration(duration_s: float) -> str:
        total_seconds = max(0, round(duration_s))
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)

        if hours:
            return f"{hours:d} h {minutes:02d} min {seconds:02d} s"

        if minutes:
            return f"{minutes:d} min {seconds:02d} s"

        return f"{seconds:d} s"