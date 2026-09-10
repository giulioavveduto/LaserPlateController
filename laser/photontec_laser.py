from __future__ import annotations

import serial
import time


class PhotontecLaser:
    REQUEST_START = 0x53
    RESPONSE_START = 0x41
    END_CODE = 0x0D

    CHANNEL_CURRENT = 0x01
    CHANNEL_EMISSION = 0x51

    COMMAND_READ = 0x00
    COMMAND_WRITE = 0x01

    def __init__(
        self,
        port: str = "/dev/ttyS4",
        baudrate: int = 115200,
        timeout: float = 2.0,
    ) -> None:
        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=8,
            parity=serial.PARITY_NONE,
            stopbits=1,
            timeout=timeout,
            write_timeout=timeout,
        )

        try:
            # Fail-safe state whenever software connects.
            self.set_emission_enabled(False)
        except Exception:
            self.ser.close()
            raise

    @staticmethod
    def _checksum(data: bytes | bytearray) -> int:
        return sum(data) & 0xFF

    def _build_request(
        self,
        channel: int,
        command: int,
        value: int = 0,
    ) -> bytes:
        if not 0 <= value <= 0xFFFF:
            raise ValueError("Laser command value must be between 0 and 65535.")

        frame = bytearray(
            [
                self.REQUEST_START,
                0x08,
                channel,
                command,
                (value >> 8) & 0xFF,
                value & 0xFF,
            ]
        )
        frame.append(self._checksum(frame))
        frame.append(self.END_CODE)
        return bytes(frame)

    def _read_exactly(self, size: int) -> bytes:
        reply = self.ser.read(size)

        if len(reply) != size:
            raise RuntimeError(
                f"Incomplete laser reply: expected {size} bytes, "
                f"received {len(reply)} ({reply.hex(' ')})."
            )

        return reply

    def _validate_reply(
        self,
        reply: bytes,
        expected_channel: int,
        expected_command: int,
        expected_size: int,
    ) -> None:
        if len(reply) != expected_size:
            raise RuntimeError(f"Invalid laser reply length: {len(reply)} bytes.")

        if reply[0] != self.RESPONSE_START:
            raise RuntimeError(f"Invalid laser response start code: 0x{reply[0]:02X}.")

        if reply[1] != expected_size:
            raise RuntimeError(f"Invalid laser frame-size byte: {reply[1]}.")

        if reply[2] != expected_channel:
            raise RuntimeError(f"Unexpected laser response channel: 0x{reply[2]:02X}.")

        if reply[3] != expected_command:
            raise RuntimeError(f"Unexpected laser response command: 0x{reply[3]:02X}.")

        if reply[-1] != self.END_CODE:
            raise RuntimeError(f"Invalid laser response end code: 0x{reply[-1]:02X}.")

        expected_checksum = self._checksum(reply[:-2])

        if reply[-2] != expected_checksum:
            raise RuntimeError(
                "Invalid laser response checksum: "
                f"received 0x{reply[-2]:02X}, "
                f"expected 0x{expected_checksum:02X}."
            )

    def _exchange(
        self,
        channel: int,
        command: int,
        value: int = 0,
        attempts: int = 3,
    ) -> bytes:
        request = self._build_request(channel, command, value)
        response_size = 8 if command == self.COMMAND_READ else 9
        last_error: Exception | None = None

        for attempt in range(attempts):
            if attempt > 0:
                time.sleep(0.2)

            try:
                self.ser.reset_input_buffer()
                self.ser.write(request)
                self.ser.flush()

                # Allow the controller to process the binary request.
                time.sleep(0.05)

                reply = self._read_exactly(response_size)
                self._validate_reply(
                    reply,
                    expected_channel=channel,
                    expected_command=command,
                    expected_size=response_size,
                )

                if command == self.COMMAND_WRITE and reply[4:7] != b"OK!":
                    raise RuntimeError(f"Laser rejected the command: {reply.hex(' ')}.")

                # Prevent the next request from arriving too quickly.
                time.sleep(0.15)
                return reply

            except (RuntimeError, serial.SerialException) as exc:
                last_error = exc

        raise RuntimeError(
            f"Laser communication failed after {attempts} attempts: " f"{last_error}"
        ) from last_error

    def get_emission_enabled(self) -> bool:
        reply = self._exchange(
            self.CHANNEL_EMISSION,
            self.COMMAND_READ,
        )
        value = int.from_bytes(reply[4:6], byteorder="big")

        if value not in (0, 1):
            raise RuntimeError(f"Invalid laser emission-state value: {value}.")

        return bool(value)

    def set_emission_enabled(self, enabled: bool) -> None:
        self._exchange(
            self.CHANNEL_EMISSION,
            self.COMMAND_WRITE,
            int(enabled),
        )

    def get_current_percent(self) -> int:
        reply = self._exchange(
            self.CHANNEL_CURRENT,
            self.COMMAND_READ,
        )
        value = int.from_bytes(reply[4:6], byteorder="big")

        if not 0 <= value <= 100:
            raise RuntimeError(f"Invalid laser current percentage: {value}.")

        return value

    def set_current_percent(self, percent: int) -> None:
        if isinstance(percent, bool) or not isinstance(percent, int):
            raise TypeError("Laser current percentage must be an integer.")

        if not 0 <= percent <= 100:
            raise ValueError("Laser current percentage must be between 0 and 100.")

        self._exchange(
            self.CHANNEL_CURRENT,
            self.COMMAND_WRITE,
            percent,
        )

    def close(self) -> None:
        if not self.ser.is_open:
            return

        try:
            self.set_emission_enabled(False)
        finally:
            self.ser.close()
