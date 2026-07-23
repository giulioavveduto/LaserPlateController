from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from stage.dmstc_stage import DMSTCStage
from simulated_stage import SimulatedStage
from stage_modes import StageMode

class StageWorker(QObject):
    connected = Signal(float, float)
    disconnected = Signal()
    position_updated = Signal(float, float)

    movement_started = Signal(float, float)
    movement_finished = Signal(float, float)

    homing_started = Signal()
    homing_finished = Signal(float, float)

    absolute_movement_started = Signal(float, float)

    error_occurred = Signal(str)

    def __init__(self) -> None:
        super().__init__()

        self.stage: Optional[DMSTCStage | SimulatedStage] = None
        self.position_timer: Optional[QTimer] = None
        self.operation_in_progress = False
        self.stage_mode = StageMode.SIMULATOR

    @Slot()
    def initialize(self) -> None:
        """Called once after the worker is moved to its thread."""
        self.position_timer = QTimer(self)
        self.position_timer.setInterval(1000)
        self.position_timer.timeout.connect(self.read_position)

    @Slot(str)
    def set_stage_mode(self, mode_value: str) -> None:
        if self.stage is not None:
            self.error_occurred.emit(
                "Disconnect the current stage before changing stage mode."
            )
            return

        try:
            self.stage_mode = StageMode(mode_value)
        except ValueError:
            self.error_occurred.emit(
                f"Unknown stage mode: {mode_value}"
            )

    @Slot()
    def connect_stage(self) -> None:
        if self.stage is not None:
            return

        try:
            if self.stage_mode is StageMode.SIMULATOR:
                self.stage = SimulatedStage()
            else:
                self.stage = DMSTCStage()

            x_mm, y_mm = self.stage.get_position_mm()

            if self.position_timer is not None:
                self.position_timer.start()

            self.connected.emit(x_mm, y_mm)

        except Exception as exc:
            self._close_stage_safely()
            self.error_occurred.emit(
                "The stage controller could not be reached.\n\n"
                "Check that:\n"
                "• the Leica DMSTC controller is powered on;\n"
                "• the cable is connected to the RS-232 port;\n"
                "• no other program is using the serial port.\n\n"
                f"Technical information:\n{exc}"
            )

    @Slot()
    def disconnect_stage(self) -> None:
        if self.position_timer is not None:
            self.position_timer.stop()

        self._close_stage_safely()
        self.disconnected.emit()

    @Slot()
    def read_position(self) -> None:
        if self.stage is None or self.operation_in_progress:
            return

        try:
            x_mm, y_mm = self.stage.get_position_mm()
            self.position_updated.emit(x_mm, y_mm)

        except Exception as exc:
            self.error_occurred.emit(
                f"Could not read the stage position:\n{exc}"
            )

    @Slot(float, float)
    def move_relative(self, dx_mm: float, dy_mm: float) -> None:
        if self.stage is None or self.operation_in_progress:
            return

        self.operation_in_progress = True
        self.movement_started.emit(dx_mm, dy_mm)

        try:
            self.stage.move_relative_mm(
                dx_mm,
                dy_mm,
                wait_seconds=2,
            )

            x_mm, y_mm = self.stage.get_position_mm()
            self.position_updated.emit(x_mm, y_mm)
            self.movement_finished.emit(x_mm, y_mm)

        except Exception as exc:
            self.error_occurred.emit(
                f"Stage movement failed:\n{exc}"
            )

        finally:
            self.operation_in_progress = False

    @Slot(float, float)
    def move_absolute(self, x_mm: float, y_mm: float) -> None:
        if self.stage is None or self.operation_in_progress:
            return

        self.operation_in_progress = True
        self.absolute_movement_started.emit(x_mm, y_mm)

        try:
            self.stage.move_absolute_mm(
                x_mm,
                y_mm,
                wait_seconds=2,
            )

            actual_x, actual_y = self.stage.get_position_mm()
            self.position_updated.emit(actual_x, actual_y)
            self.movement_finished.emit(actual_x, actual_y)

        except Exception as exc:
            self.error_occurred.emit(
                f"Absolute stage movement failed:\n{exc}"
            )

        finally:
            self.operation_in_progress = False

    @Slot()
    def home_stage(self) -> None:
        if self.stage is None or self.operation_in_progress:
            return

        self.operation_in_progress = True
        self.homing_started.emit()

        try:
            self.stage.home(wait_seconds=20)

            x_mm, y_mm = self.stage.get_position_mm()
            self.position_updated.emit(x_mm, y_mm)
            self.homing_finished.emit(x_mm, y_mm)

        except Exception as exc:
            self.error_occurred.emit(
                f"Stage homing failed:\n{exc}"
            )

        finally:
            self.operation_in_progress = False

    def _close_stage_safely(self) -> None:
        if self.stage is not None:
            try:
                self.stage.close()
            except Exception:
                pass

        self.stage = None
