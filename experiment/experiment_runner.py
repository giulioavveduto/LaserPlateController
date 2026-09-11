from __future__ import annotations

import math
import time
from enum import Enum, auto

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from experiment.experiment_protocol import ExperimentProtocol
from threading import Event


class ExperimentState(Enum):
    IDLE = auto()
    SWITCHING_OFF = auto()
    MOVING = auto()
    PREPARING = auto()
    EXPOSING = auto()
    PAUSING = auto()
    PAUSED = auto()
    HOMING = auto()
    STOPPING = auto()
    COMPLETED = auto()
    STOPPED = auto()
    ERROR = auto()


class ExperimentRunner(QObject):
    state_changed = Signal(ExperimentState)
    current_well_changed = Signal(str)
    remaining_time_changed = Signal(float)

    move_requested = Signal(str)
    home_requested = Signal()
    laser_requested = Signal(int, str, int, object)

    experiment_finished = Signal()
    experiment_stopped = Signal()
    error_occurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self.state = ExperimentState.IDLE
        self.wells: list[str] = []
        self.exposure_times_s: list[float] = []
        self.current_percents: list[int] = []
        self.completed_wells: list[str] = []
        self.executed_times_s: dict[str, float] = {}
        self._exposure_started_at: float | None = None

        self.stage_only = True
        self.stop_requested = False
        self.movement_pending = False
        self.home_pending = False
        self.last_laser_off_confirmed = False
        self.fault_latched = False
        self._after_off_action: str | None = None
        self._fault_message: str | None = None
        self.current_well_index = -1
        self.exposure_time_s = 0.0
        self.plate_type = ""

        self.exposure_remaining_s = 0.0
        self.pause_requested = False
        self.paused_before_exposure = False

        self.exposure_timer = QTimer(self)
        self.exposure_timer.setInterval(100)
        self.exposure_timer.timeout.connect(self._update_exposure)
        self.laser_cancel = Event()
        self._laser_token = 0
        self._laser_pending = None

        self.laser_timeout = QTimer(self)
        self.laser_timeout.setSingleShot(True)
        self.laser_timeout.setInterval(45000)
        self.laser_timeout.timeout.connect(self._on_laser_timeout)

    def _send_laser_command(self, action, value, callback) -> None:
        if self._laser_pending is not None:
            raise RuntimeError("A laser command is already pending.")
        if action not in {"off", "current", "on"}:
            raise ValueError("Unknown laser command.")
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError("Invalid laser current.")
        if action == "on" and value == 0:
            raise ValueError("0% wells must remain OFF.")

        self._laser_token += 1
        self._laser_pending = (self._laser_token, action, value, callback)
        self.laser_timeout.start()
        self.laser_requested.emit(self._laser_token, action, value, self.laser_cancel)

    @Slot(int, bool, int, str)
    def notify_laser_finished(
        self,
        token: int,
        enabled: bool,
        percent: int,
        error: str,
    ) -> None:
        pending = self._laser_pending
        if pending is None or token != pending[0]:
            return

        self.laser_timeout.stop()
        self._laser_pending = None
        _, action, value, callback = pending

        if not error:
            if enabled != (action == "on"):
                error = "Unexpected emission state in the laser reply."
            elif action != "off" and percent != value:
                error = "Unexpected current in the laser reply."

        if error:
            self.laser_cancel.set()

        # A fault has priority over every normal pause/stop callback.
        if self._fault_message is not None:
            off_confirmed = not enabled and "OFF UNCONFIRMED" not in error

            if off_confirmed:
                self.last_laser_off_confirmed = True
                self._finish_fault(error, off_confirmed=True)
            elif action == "off":
                self.last_laser_off_confirmed = False
                self._finish_fault(
                    error or "OFF UNCONFIRMED: emission remains ON.",
                    off_confirmed=False,
                )
            else:
                self._send_laser_command(
                    "off",
                    0,
                    self._after_fault_off,
                )
            return

        interruption_requested = self.stop_requested or self.pause_requested

        if interruption_requested and error in {"", "cancelled"}:
            target_callback = (
                self._after_stop_off if self.stop_requested else self._after_pause_off
            )

            final_stop_confirmation = (
                self.stop_requested
                and action == "off"
                and callback == self._after_final_off
            )

            if action == "off" and (
                callback == target_callback or final_stop_confirmation
            ):
                callback("")
            else:
                self._send_laser_command(
                    "off",
                    0,
                    target_callback,
                )
            return

        callback(error)

    def _on_laser_timeout(self) -> None:
        pending = self._laser_pending
        if pending is None:
            return

        self._laser_pending = None
        self.laser_timeout.stop()
        self.laser_cancel.set()

        _, action, _, callback = pending
        error = (
            "OFF UNCONFIRMED: laser confirmation timed out; "
            "the emission state is unknown."
        )

        if self._fault_message is not None:
            if action == "off":
                self._finish_fault(
                    error,
                    off_confirmed=False,
                )
            else:
                self._send_laser_command(
                    "off",
                    0,
                    self._after_fault_off,
                )
            return

        callback(error)

    @property
    def is_running(self) -> bool:
        return self.state in {
            ExperimentState.MOVING,
            ExperimentState.EXPOSING,
            ExperimentState.PAUSED,
            ExperimentState.HOMING,
            ExperimentState.STOPPING,
            ExperimentState.SWITCHING_OFF,
            ExperimentState.PREPARING,
            ExperimentState.PAUSING,
        }

    @property
    def is_paused(self) -> bool:
        return self.state is ExperimentState.PAUSED

    @property
    def current_well(self) -> str | None:
        if 0 <= self.current_well_index < len(self.wells):
            return self.wells[self.current_well_index]

        return None

    @property
    def current_exposure_time_s(self) -> float:
        if 0 <= self.current_well_index < len(self.exposure_times_s):
            return self.exposure_times_s[self.current_well_index]

        return 0.0

    @property
    def current_percent(self) -> int:
        if 0 <= self.current_well_index < len(self.current_percents):
            return self.current_percents[self.current_well_index]

        return 0

    @property
    def remaining_time_s(self) -> float:
        if self.current_well is None:
            return 0.0

        remaining_after_current = sum(
            self.exposure_times_s[self.current_well_index + 1 :]
        )

        if self.state in {
            ExperimentState.EXPOSING,
            ExperimentState.PAUSED,
        }:
            current_remaining = self.exposure_remaining_s
        else:
            current_remaining = self.current_exposure_time_s

        return max(
            0.0,
            current_remaining + remaining_after_current,
        )

    def set_state(self, state: ExperimentState) -> None:
        if state is self.state:
            return

        self.state = state
        self.state_changed.emit(state)

    def start(
        self,
        protocol: ExperimentProtocol,
        stage_only: bool = True,
    ) -> None:
        if self.is_running:
            raise RuntimeError("An experiment is already running.")

        if self.fault_latched:
            raise RuntimeError(
                "A previous safety fault is latched. "
                "Restart the application after checking the hardware."
            )

        if self._laser_pending is not None:
            raise RuntimeError("A laser command is still pending.")

        if not protocol.is_valid:
            raise ValueError("Cannot start an invalid experiment protocol.")

        exposure_times = [
            protocol.exposure_time_for(well) for well in protocol.selected_wells
        ]

        if not all(math.isfinite(value) and value > 0 for value in exposure_times):
            raise ValueError("Every selected well requires a finite positive duration.")

        current_percents: list[int] = []

        for well in protocol.selected_wells:
            if stage_only:
                current_percents.append(0)
                continue

            setpoint = protocol.laser_setpoint_for(well)

            if (
                setpoint is None
                or setpoint.mode != "current_percent"
                or not math.isfinite(setpoint.value)
                or not 0 <= setpoint.value <= 100
                or not float(setpoint.value).is_integer()
            ):
                raise ValueError(
                    f"{well} requires an integer laser current " "between 0 and 100%."
                )

            current_percents.append(int(setpoint.value))

        self.exposure_timer.stop()
        self.laser_timeout.stop()
        self.laser_cancel.clear()

        self.stage_only = stage_only
        self.plate_type = protocol.plate_type
        self.wells = list(protocol.selected_wells)
        self.exposure_times_s = exposure_times
        self.current_percents = current_percents
        self.completed_wells = []
        self.executed_times_s = {well: 0.0 for well in self.wells}
        self._exposure_started_at = None

        self.current_well_index = 0
        self.exposure_time_s = self.current_exposure_time_s
        self.exposure_remaining_s = self.exposure_time_s

        self.pause_requested = False
        self.stop_requested = False
        self.paused_before_exposure = False
        self.movement_pending = False
        self.home_pending = False
        self._after_off_action = None

        current_well = self.current_well
        if current_well is None:
            raise RuntimeError("The experiment contains no wells.")

        self.current_well_changed.emit(current_well)
        self.remaining_time_changed.emit(self.remaining_time_s)

        if self.stage_only:
            self.last_laser_off_confirmed = True
            self._move_current_well()
        else:
            self.last_laser_off_confirmed = False
            self.set_state(ExperimentState.SWITCHING_OFF)
            self._send_laser_command(
                "off",
                0,
                self._after_initial_laser_off,
            )

    def _after_initial_laser_off(self, error: str) -> None:
        if error:
            self.fault_latched = True
            self.fail(
                "Could not confirm laser emission OFF before movement:\n" f"{error}"
            )
            return

        self.last_laser_off_confirmed = True
        self._move_current_well()

    def _move_current_well(self) -> None:
        if not self.stage_only and not self.last_laser_off_confirmed:
            self.fault_latched = True
            self.fail(
                "Movement refused because laser emission OFF " "was not confirmed."
            )
            return

        self.movement_pending = True
        self.set_state(ExperimentState.MOVING)
        self.move_requested.emit(self.current_well)

    def notify_movement_finished(self) -> None:
        if not self.movement_pending:
            return

        self.movement_pending = False

        if self.state is ExperimentState.STOPPING:
            if self.stage_only:
                self.home_pending = True
                self.home_requested.emit()
            else:
                self.set_state(ExperimentState.SWITCHING_OFF)
                self._send_laser_command(
                    "off",
                    0,
                    self._after_stop_off,
                )
            return

        if self.state is not ExperimentState.MOVING:
            return

        self.exposure_remaining_s = self.exposure_time_s

        if self.pause_requested:
            if self.stage_only:
                self.pause_requested = False
                self.paused_before_exposure = True
                self.set_state(ExperimentState.PAUSED)
                self.remaining_time_changed.emit(self.remaining_time_s)
            else:
                self.set_state(ExperimentState.PAUSING)
                self._send_laser_command(
                    "off",
                    0,
                    self._after_pause_off,
                )
            return

        if self.stage_only:
            self._start_exposure()
            return

        # Reconfirm OFF after physical movement before configuring
        # the laser for the arrived well.
        self.last_laser_off_confirmed = False
        self.set_state(ExperimentState.SWITCHING_OFF)
        self._send_laser_command(
            "off",
            0,
            self._after_arrival_off,
        )

    def _after_arrival_off(self, error: str) -> None:
        if error:
            self._laser_sequence_failed(
                "Could not confirm emission OFF after movement",
                error,
            )
            return

        self.last_laser_off_confirmed = True
        self.set_state(ExperimentState.PREPARING)
        self._send_laser_command(
            "current",
            self.current_percent,
            self._after_current_applied,
        )

    def _after_current_applied(self, error: str) -> None:
        if error:
            self._laser_sequence_failed(
                "Could not apply the well laser current",
                error,
            )
            return

        if self.current_percent == 0:
            # Control/sham well: run the timing with emission OFF.
            self.last_laser_off_confirmed = True
            self._start_exposure()
            return

        self._send_laser_command(
            "on",
            self.current_percent,
            self._after_emission_on,
        )

    def _after_emission_on(self, error: str) -> None:
        if error:
            self._laser_sequence_failed(
                "Could not confirm laser emission ON",
                error,
            )
            return

        self.last_laser_off_confirmed = False
        self._start_exposure()

    def _after_pause_off(self, error: str) -> None:
        if error:
            self._laser_sequence_failed(
                "Could not confirm emission OFF while pausing",
                error,
            )
            return

        self.last_laser_off_confirmed = True
        self.pause_requested = False
        self.paused_before_exposure = True
        self.set_state(ExperimentState.PAUSED)
        self.remaining_time_changed.emit(self.remaining_time_s)

    def _after_stop_off(self, error: str) -> None:
        if error:
            self._laser_sequence_failed(
                "Could not confirm emission OFF before homing",
                error,
            )
            return

        self.last_laser_off_confirmed = True
        self.home_pending = True
        self.set_state(ExperimentState.STOPPING)
        self.home_requested.emit()

    def _laser_sequence_failed(
        self,
        context: str,
        error: str,
    ) -> None:
        self.fail(f"{context}:\n{error}")

    def _accumulate_executed_time(self) -> None:
        if self._exposure_started_at is None:
            return

        now = time.monotonic()
        elapsed_s = max(
            0.0,
            now - self._exposure_started_at,
        )
        self._exposure_started_at = now

        current_well = self.current_well
        if current_well is None:
            return

        planned_s = self.current_exposure_time_s
        previous_s = self.executed_times_s.get(
            current_well,
            0.0,
        )
        executed_s = min(
            planned_s,
            previous_s + elapsed_s,
        )

        self.executed_times_s[current_well] = executed_s
        self.exposure_remaining_s = max(
            0.0,
            planned_s - executed_s,
        )

    def _start_exposure(self) -> None:
        self.paused_before_exposure = False
        self.set_state(ExperimentState.EXPOSING)
        self.remaining_time_changed.emit(self.remaining_time_s)
        self._exposure_started_at = time.monotonic()
        self.exposure_timer.start()

    def _update_exposure(self) -> None:
        if self.state is not ExperimentState.EXPOSING:
            self.exposure_timer.stop()
            self._exposure_started_at = None
            return

        self._accumulate_executed_time()
        self.remaining_time_changed.emit(self.remaining_time_s)

        if self.exposure_remaining_s <= 0.0:
            self.exposure_timer.stop()
            self._exposure_started_at = None

            if self.stage_only:
                self._complete_current_well()
            else:
                self.set_state(ExperimentState.SWITCHING_OFF)
                self._send_laser_command(
                    "off",
                    0,
                    self._after_exposure_off,
                )

    def _after_exposure_off(self, error: str) -> None:
        if error:
            self._laser_sequence_failed(
                "Could not confirm emission OFF after exposure",
                error,
            )
            return

        self.last_laser_off_confirmed = True
        self._complete_current_well()

    def _complete_current_well(self) -> None:
        current_well = self.current_well
        if current_well is not None:
            self.executed_times_s[current_well] = self.current_exposure_time_s

        if current_well is not None and current_well not in self.completed_wells:
            self.completed_wells.append(current_well)

        self._advance_to_next_well()

    def _advance_to_next_well(self) -> None:
        self.current_well_index += 1

        if self.current_well_index >= len(self.wells):
            if not self.stage_only and not self.last_laser_off_confirmed:
                self._laser_sequence_failed(
                    "Homing refused",
                    "Laser emission OFF was not confirmed.",
                )
                return

            self.home_pending = True
            self.set_state(ExperimentState.HOMING)
            self.remaining_time_changed.emit(0.0)
            self.home_requested.emit()
            return

        current_well = self.current_well
        if current_well is None:
            self.fail("Could not determine the next well.")
            return

        self.exposure_time_s = self.current_exposure_time_s
        self.exposure_remaining_s = self.exposure_time_s
        self.current_well_changed.emit(current_well)
        self.remaining_time_changed.emit(self.remaining_time_s)

        self._move_current_well()

    def pause(self) -> None:
        if self.state not in {
            ExperimentState.MOVING,
            ExperimentState.SWITCHING_OFF,
            ExperimentState.PREPARING,
            ExperimentState.EXPOSING,
        }:
            return

        self.pause_requested = True

        if self.state is ExperimentState.EXPOSING:
            self._accumulate_executed_time()
            self.exposure_timer.stop()
            self._exposure_started_at = None
            self.paused_before_exposure = False
        else:
            self.paused_before_exposure = True

        if self.stage_only:
            if self.movement_pending:
                return

            self.pause_requested = False
            self.set_state(ExperimentState.PAUSED)
            self.remaining_time_changed.emit(self.remaining_time_s)
            return

        self.laser_cancel.set()

        # Keep MOVING displayed until physical movement finishes.
        # notify_movement_finished() will then switch emission OFF
        # and enter PAUSED before exposure.
        if self.movement_pending:
            return

        self.set_state(ExperimentState.PAUSING)

        if self._laser_pending is not None:
            return

        self._send_laser_command(
            "off",
            0,
            self._after_pause_off,
        )

    def resume(self) -> None:
        if self.state is not ExperimentState.PAUSED:
            return

        self.pause_requested = False
        self.laser_cancel.clear()

        if self.stage_only:
            self._start_exposure()
            return

        # Reconfirm OFF, reapply current and verify ON before
        # continuing the remaining exposure.
        self.last_laser_off_confirmed = False
        self.set_state(ExperimentState.SWITCHING_OFF)
        self._send_laser_command(
            "off",
            0,
            self._after_arrival_off,
        )

    def request_stop(self) -> None:
        if not self.is_running:
            return

        if self.state in {
            ExperimentState.STOPPING,
            ExperimentState.ERROR,
        }:
            return

        if self.state is ExperimentState.EXPOSING:
            self._accumulate_executed_time()

        self._exposure_started_at = None
        self.stop_requested = True
        self.pause_requested = False
        self.exposure_timer.stop()
        self.laser_cancel.set()
        self.set_state(ExperimentState.STOPPING)
        self.remaining_time_changed.emit(0.0)

        # Wait for physical movement, homing or the active serial
        # transaction to finish. Its callback will continue shutdown.
        if (
            self.movement_pending
            or self.home_pending
            or self._laser_pending is not None
        ):
            return

        if self.stage_only:
            self.home_pending = True
            self.home_requested.emit()
            return

        self._send_laser_command(
            "off",
            0,
            self._after_stop_off,
        )

    def notify_homing_finished(self) -> None:
        if not self.home_pending:
            return

        self.home_pending = False

        if self.stage_only:
            self._finish_after_home()
            return

        # Final verification after stage movement.
        self.set_state(ExperimentState.SWITCHING_OFF)
        self._send_laser_command(
            "off",
            0,
            self._after_final_off,
        )

    def _after_final_off(self, error: str) -> None:
        if error:
            self._laser_sequence_failed(
                "Could not confirm final emission OFF",
                error,
            )
            return

        self.last_laser_off_confirmed = True
        self._finish_after_home()

    def _finish_after_home(self) -> None:
        self.remaining_time_changed.emit(0.0)

        if self.stop_requested:
            self.set_state(ExperimentState.STOPPED)
            self.experiment_stopped.emit()
        else:
            self.set_state(ExperimentState.COMPLETED)
            self.experiment_finished.emit()

    def fail(self, message: str) -> None:
        if self.state is ExperimentState.EXPOSING:
            self._accumulate_executed_time()

        self._exposure_started_at = None

        self.exposure_timer.stop()
        self.pause_requested = False
        self.stop_requested = False
        self.movement_pending = False
        self.home_pending = False

        if self.stage_only:
            self.set_state(ExperimentState.ERROR)
            self.error_occurred.emit(message)
            return

        if self._fault_message is None:
            self._fault_message = message
        elif message not in self._fault_message:
            self._fault_message += f"\n\nAdditional error:\n{message}"

        self.fault_latched = True
        self.last_laser_off_confirmed = False
        self.laser_cancel.set()
        self.set_state(ExperimentState.SWITCHING_OFF)

        # If a serial command is running, its identified reply will
        # continue the fault shutdown through notify_laser_finished().
        if self._laser_pending is not None:
            return

        self._send_laser_command(
            "off",
            0,
            self._after_fault_off,
        )

    def _after_fault_off(self, error: str) -> None:
        off_confirmed = not error

        self.last_laser_off_confirmed = off_confirmed
        self._finish_fault(
            error,
            off_confirmed=off_confirmed,
        )

    def _finish_fault(
        self,
        shutdown_information: str,
        *,
        off_confirmed: bool,
    ) -> None:
        message = self._fault_message or "Experiment failed."
        self._fault_message = None

        if shutdown_information and shutdown_information != "cancelled":
            message += "\n\nLaser shutdown information:\n" f"{shutdown_information}"

        if not off_confirmed:
            message += (
                "\n\nDANGER: laser emission OFF could not be confirmed. "
                "Use the physical safety key immediately. Stage movement "
                "and homing are blocked. Restart the application only "
                "after checking the hardware."
            )

        self.last_laser_off_confirmed = off_confirmed
        self.set_state(ExperimentState.ERROR)
        self.error_occurred.emit(message)
