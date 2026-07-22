from __future__ import annotations

import time


class SimulatedStage:
    def __init__(
        self,
        x_limit_mm: float = 120.0,
        y_limit_mm: float = 80.0,
        movement_delay_s: float = 0.3,
    ) -> None:
        self.x_mm = 0.0
        self.y_mm = 0.0

        self.x_limit_mm = x_limit_mm
        self.y_limit_mm = y_limit_mm
        self.movement_delay_s = movement_delay_s

        self.connected = True

    def close(self) -> None:
        self.connected = False

    def _check_connected(self) -> None:
        if not self.connected:
            raise RuntimeError("The simulated stage is disconnected.")

    def _check_limits(
        self,
        x_mm: float,
        y_mm: float,
    ) -> None:
        if not 0.0 <= x_mm <= self.x_limit_mm:
            raise ValueError(
                f"X position {x_mm:.3f} mm is outside the simulated "
                f"range 0–{self.x_limit_mm:.3f} mm."
            )

        if not 0.0 <= y_mm <= self.y_limit_mm:
            raise ValueError(
                f"Y position {y_mm:.3f} mm is outside the simulated "
                f"range 0–{self.y_limit_mm:.3f} mm."
            )

    def home(self, wait_seconds: float = 0.5) -> None:
        self._check_connected()

        time.sleep(min(wait_seconds, 0.5))

        self.x_mm = 0.0
        self.y_mm = 0.0

    def get_position_mm(self) -> tuple[float, float]:
        self._check_connected()
        return self.x_mm, self.y_mm

    def move_relative_mm(
        self,
        dx_mm: float,
        dy_mm: float,
        wait_seconds: float = 0.3,
    ) -> None:
        self._check_connected()

        target_x = self.x_mm + dx_mm
        target_y = self.y_mm + dy_mm

        self._check_limits(target_x, target_y)

        time.sleep(min(wait_seconds, self.movement_delay_s))

        self.x_mm = target_x
        self.y_mm = target_y

    def move_absolute_mm(
        self,
        x_mm: float,
        y_mm: float,
        wait_seconds: float = 0.3,
    ) -> None:
        self._check_connected()
        self._check_limits(x_mm, y_mm)

        time.sleep(min(wait_seconds, self.movement_delay_s))

        self.x_mm = x_mm
        self.y_mm = y_mm