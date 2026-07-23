from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import QObject, Signal


class ExperimentState(Enum):
    IDLE = auto()
    MOVING = auto()
    EXPOSING = auto()
    COMPLETED = auto()
    STOPPED = auto()
    ERROR = auto()


class ExperimentRunner(QObject):
    state_changed = Signal(ExperimentState)
    current_well_changed = Signal(str)
    remaining_time_changed = Signal(float)
    experiment_finished = Signal()
    error_occurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self.state = ExperimentState.IDLE
        self.wells: list[str] = []
        self.current_well_index = -1
        self.exposure_time_s = 0.0

    @property
    def is_running(self) -> bool:
        return self.state in {
            ExperimentState.MOVING,
            ExperimentState.EXPOSING,
        }

    @property
    def current_well(self) -> str | None:
        if 0 <= self.current_well_index < len(self.wells):
            return self.wells[self.current_well_index]

        return None

    def set_state(self, state: ExperimentState) -> None:
        if state is self.state:
            return

        self.state = state
        self.state_changed.emit(state)