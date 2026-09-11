from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from experiment.experiment_protocol import ExperimentProtocol


class FocusWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


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

        group = QGroupBox("Experiment progress")
        form_layout = QGridLayout(group)

        self.selected_wells_label = QLabel()
        self.estimated_duration_label = QLabel()
        self.validity_label = QLabel()

        self.experiment_state_label = QLabel("Idle")
        self.current_well_label = QLabel("--")
        self.sequence_position_label = QLabel("--")
        self.current_exposure_label = QLabel("--")
        self.remaining_time_label = QLabel("--")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0 / 0 wells completed")

        fields = [
            ("Selected wells:", self.selected_wells_label),
            ("Estimated exposure:", self.estimated_duration_label),
            ("Timing status:", self.validity_label),
            ("Experiment state:", self.experiment_state_label),
            ("Current well:", self.current_well_label),
            ("Sequence position:", self.sequence_position_label),
            ("Current exposure:", self.current_exposure_label),
            ("Exposure remaining:", self.remaining_time_label),
        ]
        for index, (title, value) in enumerate(fields):
            row, column = divmod(index, 4)
            form_layout.addWidget(QLabel(title), row * 2, column)
            form_layout.addWidget(value, row * 2 + 1, column)
        form_layout.addWidget(self.progress_bar, 4, 0, 1, 4)

        main_layout.addWidget(group)

        self.refresh()
        self.reset_dashboard()

    def refresh(self) -> None:
        self.selected_wells_label.setText(str(self.protocol.selected_well_count))

        self.estimated_duration_label.setText(
            self.format_duration(self.protocol.estimated_duration_s)
        )

        if self.protocol.is_valid:
            self.validity_label.setText("Valid")
            self.validity_label.setStyleSheet("font-weight: bold; color: #16803a;")
        else:
            self.validity_label.setText("Incomplete")
            self.validity_label.setStyleSheet("font-weight: bold; color: #a12626;")

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
            self.sequence_position_label.setText(f"{current_index + 1} / {total_wells}")
        else:
            self.sequence_position_label.setText("--")

        self.current_exposure_label.setText(
            self.format_duration(current_exposure_remaining_s)
        )
        self.remaining_time_label.setText(self.format_duration(total_remaining_s))

        completed_wells = max(
            0,
            min(completed_wells, total_wells),
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
            return f"{hours:d} h {minutes:02d} min " f"{seconds:02d} s"

        if minutes:
            return f"{minutes:d} min {seconds:02d} s"

        return f"{seconds:d} s"
