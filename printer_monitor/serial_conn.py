"""Serial connection and polling for Marlin firmware."""

import logging
import threading
from time import sleep, time

import serial

from .parsers import parse_m27, parse_m105, parse_m114, parse_m220
from .state import PrinterState

logger = logging.getLogger(__name__)

BUSY_PREFIX = "echo:busy: processing"


class SerialConnection:
    """Manages serial communication with the printer."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 2.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: serial.Serial | None = None

    def open(self) -> None:
        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            timeout=self.timeout,
        )
        logger.info("Opened serial port %s at %d baud", self.port, self.baudrate)

    def close(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Closed serial port %s", self.port)

    def flush_input(self) -> None:
        """Discard any stale data in the input buffer."""
        if self._serial and self._serial.is_open:
            self._serial.reset_input_buffer()

    def send_command(self, command: str, timeout: float = 5.0) -> list[str]:
        """Send a G-code command and collect response lines until 'ok'.

        Handles 'echo:busy: processing' by extending the timeout.
        Returns all collected lines (including the 'ok' line).
        """
        if not self._serial or not self._serial.is_open:
            raise ConnectionError("Serial port not open")

        self.flush_input()

        cmd = command.strip() + "\n"
        self._serial.write(cmd.encode("ascii"))
        logger.debug("TX: %s", command.strip())

        lines: list[str] = []
        deadline = time() + timeout

        while time() < deadline:
            raw = self._serial.readline()
            if not raw:
                continue

            line = raw.decode("ascii", errors="replace").strip()
            if not line:
                continue

            logger.debug("RX: %s", line)

            if line.startswith(BUSY_PREFIX):
                # Printer is alive but busy — extend deadline
                deadline = time() + timeout
                continue

            lines.append(line)

            if line.startswith("ok"):
                return lines

        logger.warning("Timeout waiting for 'ok' after command: %s", command)
        return lines


class PrinterPoller(threading.Thread):
    """Background thread that polls the printer at regular intervals."""

    def __init__(
        self,
        conn: SerialConnection,
        state: PrinterState,
        interval: float = 2.5,
    ):
        super().__init__(daemon=True, name="printer-poller")
        self.conn = conn
        self.state = state
        self.interval = interval
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            self.conn.open()
            self.state.connected = True
            self.state.last_update = time()
            logger.info("Poller started, interval=%.1fs", self.interval)
        except (serial.SerialException, OSError) as exc:
            self.state.last_error = str(exc)
            logger.error("Failed to open serial port: %s", exc)
            return

        while not self._stop_event.is_set():
            try:
                self._poll_once()
                self.state.connected = True
                self.state.last_error = ""
                self.state.last_update = time()
            except (serial.SerialException, OSError, ConnectionError) as exc:
                self.state.connected = False
                self.state.last_error = str(exc)
                logger.error("Poll error: %s", exc)
                break

            # Sleep in small increments so Ctrl+C is responsive
            for _ in range(int(self.interval / 0.1)):
                if self._stop_event.is_set():
                    return
                sleep(0.1)

        self.conn.close()

    def _poll_once(self) -> None:
        """Send all status commands and update state."""
        # M105 — temperatures
        lines = self.conn.send_command("M105")
        for line in lines:
            temps = parse_m105(line)
            if temps:
                if "hotend0" in temps:
                    self.state.hotend0 = temps["hotend0"]
                if "hotend1" in temps:
                    self.state.hotend1 = temps["hotend1"]
                if "bed" in temps:
                    self.state.bed = temps["bed"]
                break

        # M27 — SD progress
        lines = self.conn.send_command("M27")
        for line in lines:
            printing, done, total = parse_m27(line)
            if printing or "Not SD printing" in line:
                self.state.sd_printing = printing
                self.state.sd_bytes_done = done
                self.state.sd_bytes_total = total
                break

        # M114 — position
        lines = self.conn.send_command("M114")
        for line in lines:
            pos = parse_m114(line)
            if pos:
                self.state.x = pos.get("x", self.state.x)
                self.state.y = pos.get("y", self.state.y)
                self.state.z = pos.get("z", self.state.z)
                self.state.e = pos.get("e", self.state.e)
                break

        # M220 — feedrate
        lines = self.conn.send_command("M220")
        for line in lines:
            fr = parse_m220(line)
            if fr is not None:
                self.state.feedrate_percent = fr
                break
