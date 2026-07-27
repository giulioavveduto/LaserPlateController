from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QProgressBar,
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
        self.sequence_position_label = QLabel("--")
        self.current_exposure_label = QLabel("--")
        self.remaining_time_label = QLabel("--")
        self.completed_wells_label = QLabel("0 / 0")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0 / 0 wells completed")

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
            "Sequence position:",
            self.sequence_position_label,
        )
        form_layout.addRow(
            "Current exposure:",
            self.current_exposure_label,
        )
        form_layout.addRow(
            "Total remaining time:",
            self.remaining_time_label,
        )
        form_layout.addRow(
            "Completed wells:",
            self.completed_wells_label,
        )
        form_layout.addRow(
            "Overall progress:",
            self.progress_bar,
        )

        main_layout.addWidget(group)

        self.refresh()
        self.reset_dashboard()

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

    def update_dashboard(
        self,
        *,
        state_text: str,
        current_well: str | None,
        current_index: int,
        total_wells: int,
        completed_wells: int,
        current_exposure_remaining_s: float,
        total_remaining_s: float,
    ) -> None:
        self.experiment_state_label.setText(state_text)
        self.current_well_label.setText(current_well or "--")

        if current_well is not None and total_wells > 0:
            self.sequence_position_label.setText(
                f"{current_index + 1} / {total_wells}"
            )
        else:
            self.sequence_position_label.setText("--")

        self.current_exposure_label.setText(
            self.format_duration(current_exposure_remaining_s)
        )
        self.remaining_time_label.setText(
            self.format_duration(total_remaining_s)
        )

        completed_wells = max(
            0,
            min(completed_wells, total_wells),
        )

        self.completed_wells_label.setText(
            f"{completed_wells} / {total_wells}"
        )

        self.progress_bar.setRange(0, max(1, total_wells))
        self.progress_bar.setValue(completed_wells)
        self.progress_bar.setFormat(
            f"{completed_wells} / {total_wells} wells completed"
        )

    def reset_dashboard(self) -> None:
        self.update_dashboard(
            state_text="Idle",
            current_well=None,
            current_index=-1,
            total_wells=0,
            completed_wells=0,
            current_exposure_remaining_s=0.0,
            total_remaining_s=0.0,
        )

    @staticmethod
    def format_duration(duration_s: float) -> str:
        total_seconds = max(0, round(duration_s))
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)

        if hours:
            return (
                f"{hours:d} h {minutes:02d} min "
                f"{seconds:02d} s"
            )

        if minutes:
            return f"{minutes:d} min {seconds:02d} s"

        return f"{seconds:d} s"