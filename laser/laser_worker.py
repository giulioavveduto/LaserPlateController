from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from laser.laser_modes import LaserMode
from laser.photontec_laser import PhotontecLaser
from laser.simulated_laser import SimulatedLaser


class LaserWorker(QObject):
    connected = Signal(bool, int)
    disconnected = Signal()
    status_updated = Signal(bool, int)
    error_occurred = Signal(str)

    def __init__(self) -> None:
        super().__init__()

        self.laser: Optional[PhotontecLaser | SimulatedLaser] = None
        self.status_timer: Optional[QTimer] = None
        self.operation_in_progress = False
        self.laser_mode = LaserMode.SIMULATOR

    @Slot()
    def initialize(self) -> None:
        """Called once after the worker is moved to its thread."""
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(1000)
        self.status_timer.timeout.connect(self.read_status)

    @Slot(str)
    def set_laser_mode(self, mode_value: str) -> None:
        if self.laser is not None:
            self.error_occurred.emit(
                "Disconnect the current laser before changing laser mode."
            )
            return

        try:
            self.laser_mode = LaserMode(mode_value)
        except ValueError:
            self.error_occurred.emit(f"Unknown laser mode: {mode_value}")

    @Slot()
    def connect_laser(self) -> None:
        if self.laser is not None:
            return

        try:
            if self.laser_mode is LaserMode.SIMULATOR:
                self.laser = SimulatedLaser()
            else:
                self.laser = PhotontecLaser()

            emission_enabled, current_percent = self._read_status_values()

            if self.status_timer is not None:
                self.status_timer.start()

            self.connected.emit(
                emission_enabled,
                current_percent,
            )
            self.status_updated.emit(
                emission_enabled,
                current_percent,
            )

        except Exception as exc:
            self._close_laser_safely()
            self.error_occurred.emit(
                "The laser controller could not be reached.\n\n"
                "Check that:\n"
                "• the laser controller is powered on;\n"
                "• the RS-232 cable is connected to /dev/ttyS4;\n"
                "• no other program is using the serial port;\n"
                "• the serial configuration is 115200 baud, 8N1.\n\n"
                f"Technical information:\n{exc}"
            )

    @Slot()
    def disconnect_laser(self) -> None:
        if self.status_timer is not None:
            self.status_timer.stop()

        close_error = self._close_laser_safely()
        self.disconnected.emit()

        if close_error is not None:
            self.error_occurred.emit(
                "The laser connection was closed, but the software "
                "could not confirm that emission was switched OFF.\n\n"
                f"Technical information:\n{close_error}"
            )

    @Slot()
    def read_status(self) -> None:
        if self.laser is None or self.operation_in_progress:
            return

        try:
            emission_enabled, current_percent = self._read_status_values()
            self.status_updated.emit(
                emission_enabled,
                current_percent,
            )

        except Exception as exc:
            self._fail_and_disconnect(f"Could not read the laser status:\n{exc}")

    @Slot(int)
    def set_current_percent(self, percent: int) -> None:
        if self.laser is None or self.operation_in_progress:
            return

        self.operation_in_progress = True

        try:
            self.laser.set_current_percent(percent)
            emission_enabled, actual_percent = self._read_status_values()

            if actual_percent != percent:
                raise RuntimeError(
                    "The laser did not retain the requested current: "
                    f"requested {percent}%, reported {actual_percent}%."
                )

            self.status_updated.emit(
                emission_enabled,
                actual_percent,
            )

        except Exception as exc:
            self._fail_and_disconnect(f"Could not set the laser current:\n{exc}")

        finally:
            self.operation_in_progress = False

    @Slot(bool)
    def set_emission_enabled(self, enabled: bool) -> None:
        if self.laser is None or self.operation_in_progress:
            return

        self.operation_in_progress = True

        try:
            self.laser.set_emission_enabled(enabled)
            actual_enabled, current_percent = self._read_status_values()

            if actual_enabled != enabled:
                raise RuntimeError(
                    "The laser did not retain the requested emission state."
                )

            self.status_updated.emit(
                actual_enabled,
                current_percent,
            )

        except Exception as exc:
            self._fail_and_disconnect(
                f"Could not change the laser emission state:\n{exc}"
            )

        finally:
            self.operation_in_progress = False

    def _read_status_values(self) -> tuple[bool, int]:
        if self.laser is None:
            raise RuntimeError("The laser is not connected.")

        emission_enabled = self.laser.get_emission_enabled()
        current_percent = self.laser.get_current_percent()

        return emission_enabled, current_percent

    def _fail_and_disconnect(self, message: str) -> None:
        if self.status_timer is not None:
            self.status_timer.stop()

        close_error = self._close_laser_safely()
        self.disconnected.emit()

        if close_error is not None:
            message += (
                "\n\nWARNING: emission OFF could not be confirmed. "
                "Use the physical safety key.\n\n"
                f"Shutdown error:\n{close_error}"
            )

        self.error_occurred.emit(message)

    def _close_laser_safely(self) -> Exception | None:
        close_error: Exception | None = None

        if self.laser is not None:
            try:
                self.laser.close()
            except Exception as exc:
                close_error = exc

        self.laser = None
        return close_error
