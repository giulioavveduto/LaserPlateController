import time
import serial


class DMSTCStage:
    UNITS_PER_MM = 39370.07874

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

    def _query(self, command: str) -> str:
        self.ser.reset_input_buffer()
        self.ser.write((command + "\r").encode())
        reply = self.ser.read(100).decode(errors="replace").strip()
        return reply

    def home(self, wait_seconds=20):
        self.ser.reset_input_buffer()
        self.ser.write(b"10011\r")
        time.sleep(wait_seconds)

        x, y = self.get_position_units()
        if x != 0 or y != 0:
            raise RuntimeError(f"Homing failed: X={x}, Y={y}")

    def get_position_units(self):
        x_reply = self._query("10016")
        y_reply = self._query("10017")

        if "???" in x_reply or "???" in y_reply:
            raise RuntimeError(
                "Stage position is undefined. Home the stage first."
            )

        x = int(x_reply[5:])
        y = int(y_reply[5:])
        return x, y

    def get_position_mm(self):
        x, y = self.get_position_units()
        return x / self.UNITS_PER_MM, y / self.UNITS_PER_MM

    def move_relative_units(self, dx: int, dy: int, wait_seconds=2):
        command = f"10005{dx} {dy}\r"
        self.ser.reset_input_buffer()
        self.ser.write(command.encode())
        time.sleep(wait_seconds)

    def move_relative_mm(self, dx_mm: float, dy_mm: float, wait_seconds=2):
        dx = round(dx_mm * self.UNITS_PER_MM)
        dy = round(dy_mm * self.UNITS_PER_MM)
        self.move_relative_units(dx, dy, wait_seconds)

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

        x_units = round(x_mm * self.UNITS_PER_MM)
        y_units = round(y_mm * self.UNITS_PER_MM)

        self.move_absolute_units(
            x_units,
            y_units,
            wait_seconds,
        )
