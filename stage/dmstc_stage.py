import time
import serial
import re
import time
import serial


class DMSTCStage:
    UNITS_PER_MM = 39370.07874
    X_SCALE = 0.98390
    X_OFFSET_MM = 0.2565

    Y_SCALE = 0.98507
    Y_OFFSET_MM = 0.2833

    def __init__(self, port="/dev/ttyS0", baudrate=19200, timeout=3):
        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=8,
            parity=serial.PARITY_NONE,
            stopbits=1,
            timeout=timeout,
        )

    def close(self):
        self.ser.close()

    def _query(
        self,
        command: str,
        attempts: int = 5,
        retry_delay: float = 0.30,
    ) -> str:
        last_reply = ""

        for _ in range(attempts):
            self.ser.reset_input_buffer()
            self.ser.write((command + "\r").encode())
            self.ser.flush()

            reply = self.ser.read_until(b"\r").decode(errors="replace").strip()

            last_reply = reply

            if re.fullmatch(
                rf"{re.escape(command)}[+-]?\d+",
                reply,
            ):
                return reply

            time.sleep(retry_delay)

        raise RuntimeError(
            f"No valid reply received for command {command!r}. "
            f"Last reply: {last_reply!r}"
        )

    def home(self, wait_seconds=20):
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

        self.ser.write(b"10011\r")
        self.ser.flush()

        time.sleep(wait_seconds)

        # Allow the controller to return to command mode.
        time.sleep(1.0)
        self.ser.reset_input_buffer()

        x, y = self.get_position_units()

        if x != 0 or y != 0:
            raise RuntimeError(f"Homing failed: X={x}, Y={y}")

    def get_position_units(self):
        x_reply = self._query("10016")
        y_reply = self._query("10017")

        if "???" in x_reply or "???" in y_reply:
            raise RuntimeError("Stage position is undefined. Home the stage first.")

        x_value = x_reply[5:].strip()
        y_value = y_reply[5:].strip()

        if not x_value or not y_value:
            raise RuntimeError(
                "Incomplete stage position response: " f"X={x_reply!r}, Y={y_reply!r}"
            )

        try:
            x = int(x_value)
            y = int(y_value)
        except ValueError as exc:
            raise RuntimeError(
                "Invalid stage position response: " f"X={x_reply!r}, Y={y_reply!r}"
            ) from exc

        return x, y

    @staticmethod
    def _controller_to_physical_mm(
        controller_mm: float,
        scale: float,
        offset_mm: float,
    ) -> float:
        if controller_mm == 0:
            return 0.0

        return offset_mm + scale * controller_mm

    @staticmethod
    def _physical_to_controller_mm(
        physical_mm: float,
        scale: float,
        offset_mm: float,
    ) -> float:
        if physical_mm == 0:
            return 0.0

        return (physical_mm - offset_mm) / scale

    def get_position_mm(self):
        x_units, y_units = self.get_position_units()

        x_controller_mm = x_units / self.UNITS_PER_MM
        y_controller_mm = y_units / self.UNITS_PER_MM

        x_physical_mm = self._controller_to_physical_mm(
            x_controller_mm,
            self.X_SCALE,
            self.X_OFFSET_MM,
        )
        y_physical_mm = self._controller_to_physical_mm(
            y_controller_mm,
            self.Y_SCALE,
            self.Y_OFFSET_MM,
        )

        return x_physical_mm, y_physical_mm

    def move_relative_units(self, dx: int, dy: int, wait_seconds=2):
        command = f"10005{dx} {dy}\r"
        self.ser.reset_input_buffer()
        self.ser.write(command.encode())
        time.sleep(wait_seconds)

    def move_relative_mm(
        self,
        dx_mm: float,
        dy_mm: float,
        wait_seconds=2,
    ):
        dx_controller_mm = dx_mm / self.X_SCALE
        dy_controller_mm = dy_mm / self.Y_SCALE

        dx_units = round(dx_controller_mm * self.UNITS_PER_MM)
        dy_units = round(dy_controller_mm * self.UNITS_PER_MM)

        self.move_relative_units(
            dx_units,
            dy_units,
            wait_seconds,
        )

    def move_absolute_units(
        self,
        x_units: int,
        y_units: int,
        wait_seconds: float = 2,
    ) -> None:
        command = f"10002{x_units} {y_units}\r"
        self.ser.reset_input_buffer()
        self.ser.write(command.encode())
        time.sleep(wait_seconds)

    def move_absolute_mm(
        self,
        x_mm: float,
        y_mm: float,
        wait_seconds: float = 2,
    ) -> None:
        if x_mm < 0 or y_mm < 0:
            raise ValueError("Absolute coordinates cannot be negative.")

        x_controller_mm = self._physical_to_controller_mm(
            x_mm,
            self.X_SCALE,
            self.X_OFFSET_MM,
        )
        y_controller_mm = self._physical_to_controller_mm(
            y_mm,
            self.Y_SCALE,
            self.Y_OFFSET_MM,
        )

        if x_controller_mm < 0 or y_controller_mm < 0:
            raise ValueError("Requested coordinates are below the calibrated range.")

        x_units = round(x_controller_mm * self.UNITS_PER_MM)
        y_units = round(y_controller_mm * self.UNITS_PER_MM)

        self.move_absolute_units(
            x_units,
            y_units,
            wait_seconds,
        )
        self.move_absolute_units(
            x_units,
            y_units,
            wait_seconds,
        )
