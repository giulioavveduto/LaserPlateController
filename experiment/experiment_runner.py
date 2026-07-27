from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import QObject, QTimer, Signal

from experiment.experiment_protocol import ExperimentProtocol


class ExperimentState(Enum):
    IDLE = auto()
    MOVING = auto()
    EXPOSING = auto()
    HOMING = auto()
    COMPLETED = auto()
    STOPPED = auto()
    ERROR = auto()


class ExperimentRunner(QObject):
    state_changed = Signal(ExperimentState)
    current_well_changed = Signal(str)
    remaining_time_changed = Signal(float)

    move_requested = Signal(str)
    home_requested = Signal()

    experiment_finished = Signal()
    error_occurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self.state = ExperimentState.IDLE
        self.wells: list[str] = []
        self.current_well_index = -1
        self.exposure_time_s = 0.0
        self.plate_type = ""

        self.exposure_remaining_s = 0.0

        self.exposure_timer = QTimer(self)
        self.exposure_timer.setInterval(100)
        self.exposure_timer.timeout.connect(self._update_exposure)

    @property
    def is_running(self) -> bool:
        return self.state in {
            ExperimentState.MOVING,
            ExperimentState.EXPOSING,
            ExperimentState.HOMING,
        }

    @property
    def current_well(self) -> str | None:
        if 0 <= self.current_well_index < len(self.wells):
            return self.wells[self.current_well_index]

        return None

    @property
    def remaining_time_s(self) -> float:
        remaining_after_current = max(
            0,
            len(self.wells) - self.current_well_index - 1,
        )

        current_remaining = (
            self.exposure_remaining_s
            if self.state is ExperimentState.EXPOSING
            else (
                self.exposure_time_s
                if self.current_well is not None
                else 0.0
            )
        )

        return max(
            0.0,
            current_remaining
            + remaining_after_current * self.exposure_time_s,
        )

    def set_state(self, state: ExperimentState) -> None:
        if state is self.state:
            return

        self.state = state
        self.state_changed.emit(state)

    def start(self, protocol: ExperimentProtocol) -> None:
        if self.is_running:
            raise RuntimeError("An experiment is already running.")

        if not protocol.is_valid:
            raise ValueError("Cannot start an invalid experiment protocol.")

        self.exposure_timer.stop()

        # Snapshot all execution-relevant values.
        self.plate_type = protocol.plate_type
        self.wells = list(protocol.selected_wells)
        self.exposure_time_s = protocol.common_exposure_time_s
        self.current_well_index = 0
        self.exposure_remaining_s = self.exposure_time_s

        current_well = self.current_well

        if current_well is None:
            raise RuntimeError("The experiment contains no wells.")

        self.current_well_changed.emit(current_well)
        self.remaining_time_changed.emit(self.remaining_time_s)
        self.set_state(ExperimentState.MOVING)
        self.move_requested.emit(current_well)

    def notify_movement_finished(self) -> None:
        if self.state is not ExperimentState.MOVING:
            return

        self.exposure_remaining_s = self.exposure_time_s
        self.set_state(ExperimentState.EXPOSING)
        self.remaining_time_changed.emit(self.remaining_time_s)
        self.exposure_timer.start()

    def _update_exposure(self) -> None:
        if self.state is not ExperimentState.EXPOSING:
            self.exposure_timer.stop()
            return

        self.exposure_remaining_s = max(
            0.0,
            self.exposure_remaining_s - 0.1,
        )
        self.remaining_time_changed.emit(self.remaining_time_s)

        if self.exposure_remaining_s <= 0.0:
            self.exposure_timer.stop()
            self._advance_to_next_well()

    def _advance_to_next_well(self) -> None:
        self.current_well_index += 1

        if self.current_well_index >= len(self.wells):
            self.set_state(ExperimentState.HOMING)
            self.remaining_time_changed.emit(0.0)
            self.home_requested.emit()
            return

        current_well = self.current_well

        if current_well is None:
            self.fail("Could not determine the next well.")
            return

        self.exposure_remaining_s = self.exposure_time_s
        self.current_well_changed.emit(current_well)
        self.set_state(ExperimentState.MOVING)
        self.remaining_time_changed.emit(self.remaining_time_s)
        self.move_requested.emit(current_well)

    def notify_homing_finished(self) -> None:
        if self.state is not ExperimentState.HOMING:
            return

        self.set_state(ExperimentState.COMPLETED)
        self.remaining_time_changed.emit(0.0)
        self.experiment_finished.emit()

    def stop(self) -> None:
        if not self.is_running:
            return

        self.exposure_timer.stop()
        self.set_state(ExperimentState.STOPPED)
        self.remaining_time_changed.emit(0.0)

    def fail(self, message: str) -> None:
        self.exposure_timer.stop()
        self.set_state(ExperimentState.ERROR)
        self.error_occurred.emit(message)