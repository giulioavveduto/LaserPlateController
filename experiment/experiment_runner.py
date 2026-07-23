from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import QObject, Signal

from experiment.experiment_protocol import ExperimentProtocol


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
        self.plate_type = ""

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

    @property
    def remaining_time_s(self) -> float:
        if self.current_well_index < 0:
            remaining_wells = len(self.wells)
        else:
            remaining_wells = len(self.wells) - self.current_well_index

        return max(0.0, remaining_wells * self.exposure_time_s)

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

        # Snapshot all execution-relevant values.
        self.plate_type = protocol.plate_type
        self.wells = list(protocol.selected_wells)
        self.exposure_time_s = protocol.common_exposure_time_s
        self.current_well_index = 0

        current_well = self.current_well

        if current_well is None:
            raise RuntimeError("The experiment contains no wells.")

        self.current_well_changed.emit(current_well)
        self.remaining_time_changed.emit(self.remaining_time_s)
        self.set_state(ExperimentState.MOVING)