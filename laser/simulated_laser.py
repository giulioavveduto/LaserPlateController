from __future__ import annotations

import time


class SimulatedLaser:
    def __init__(
        self,
        command_delay_s: float = 0.05,
    ) -> None:
        self.current_percent = 0
        self.emission_enabled = False
        self.command_delay_s = command_delay_s
        self.connected = True

    def _check_connected(self) -> None:
        if not self.connected:
            raise RuntimeError("The simulated laser is disconnected.")

    def get_emission_enabled(self) -> bool:
        self._check_connected()
        return self.emission_enabled

    def set_emission_enabled(self, enabled: bool) -> None:
        self._check_connected()

        if not isinstance(enabled, bool):
            raise TypeError("Laser emission state must be boolean.")

        time.sleep(self.command_delay_s)
        self.emission_enabled = enabled

    def get_current_percent(self) -> int:
        self._check_connected()
        return self.current_percent

    def set_current_percent(self, percent: int) -> None:
        self._check_connected()

        if isinstance(percent, bool) or not isinstance(percent, int):
            raise TypeError("Laser current percentage must be an integer.")

        if not 0 <= percent <= 100:
            raise ValueError("Laser current percentage must be between 0 and 100.")

        time.sleep(self.command_delay_s)
        self.current_percent = percent

    def close(self) -> None:
        if not self.connected:
            return

        self.emission_enabled = False
        self.connected = False
