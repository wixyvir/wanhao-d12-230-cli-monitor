"""Serial connection and polling for Marlin firmware."""

import glob
import logging
import os
import threading
from time import sleep, time

import serial

from .parsers import parse_m27, parse_m105, parse_m114, parse_m220
from .state import PrinterState

logger = logging.getLogger(__name__)

BUSY_PREFIX = "echo:busy: processing"
NO_RESPONSE_ERROR = "No response from printer"

BY_ID_DIR = "/dev/serial/by-id"
FALLBACK_GLOB = "/dev/ttyUSB*"


def find_by_id_link(device: str, by_id_dir: str | None = None) -> str | None:
    """Return the stable /dev/serial/by-id symlink pointing to `device`, if any."""
    by_id_dir = by_id_dir or BY_ID_DIR
    try:
        names = sorted(os.listdir(by_id_dir))
    except OSError:
        return None

    target = os.path.realpath(device)
    for name in names:
        link = os.path.join(by_id_dir, name)
        if os.path.realpath(link) == target:
            return link
    return None


def resolve_port(
    configured: str,
    by_id_link: str | None = None,
    fallback_glob: str | None = None,
) -> str:
    """Pick the device path to open, following USB re-enumeration.

    Order: the by-id link remembered from a previous open (it identifies the
    exact device), then the configured path, then the only device matching
    `fallback_glob`. Never guesses when several devices match; returns the
    configured path so the open fails with a clear error and is retried.
    """
    if by_id_link and os.path.exists(by_id_link):
        return by_id_link
    if os.path.exists(configured):
        return configured

    candidates = glob.glob(fallback_glob or FALLBACK_GLOB)
    if len(candidates) == 1:
        return candidates[0]
    return configured


def _got_ok(lines: list[str]) -> bool:
    return bool(lines) and lines[-1].startswith("ok")


class SerialConnection:
    """Manages serial communication with the printer."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 2.0):
        self.port = port
        self.active_port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: serial.Serial | None = None
        self._by_id_link: str | None = None

    def open(self) -> None:
        self.close()

        path = resolve_port(self.port, self._by_id_link)
        self._serial = serial.Serial(
            port=path,
            baudrate=self.baudrate,
            timeout=self.timeout,
        )
        self.active_port = path
        self._by_id_link = find_by_id_link(path) or self._by_id_link

        if path != self.port:
            logger.info("Configured port %s resolved to %s", self.port, path)
        logger.info("Opened serial port %s at %d baud", path, self.baudrate)

    def close(self) -> None:
        """Close the port. Never raises: the device may already be gone."""
        if self._serial is None:
            return
        try:
            self._serial.close()
            logger.info("Closed serial port %s", self.active_port)
        except Exception as exc:
            logger.debug("Error closing serial port %s: %s", self.active_port, exc)
        finally:
            self._serial = None

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

    def _reconnect(self) -> bool:
        """Try to reconnect, sleeping between attempts. Returns False if stopped."""
        while not self._stop_event.is_set():
            for _ in range(int(self.interval / 0.1)):
                if self._stop_event.is_set():
                    return False
                sleep(0.1)
            try:
                self.conn.open()
                self.state.connected = True
                self.state.last_error = ""
                self.state.last_update = time()
                logger.info("Reconnected to %s", self.conn.port)
                return True
            except Exception as exc:
                self.state.last_error = str(exc)
                logger.debug("Reconnect attempt failed: %s", exc)
        return False

    def run(self) -> None:
        try:
            self._run()
        finally:
            # Whatever ends the thread, never report a live connection afterwards
            self.state.connected = False
            self.conn.close()

    def _run(self) -> None:
        try:
            self.conn.open()
            self.state.connected = True
            self.state.last_update = time()
            logger.info("Poller started, interval=%.1fs", self.interval)
        except Exception as exc:
            self.state.last_error = str(exc)
            logger.error("Failed to open serial port: %s", exc)
            if not self._reconnect():
                return

        while not self._stop_event.is_set():
            try:
                responded = self._poll_once()
            except Exception as exc:
                # Catch everything: e.g. termios.error is not an OSError, and
                # letting it escape would silently kill this thread.
                self.state.connected = False
                self.state.last_error = str(exc) or type(exc).__name__
                logger.exception("Poll error")
                self.conn.close()
                if not self._reconnect():
                    break
            else:
                if responded:
                    self.state.connected = True
                    self.state.last_error = ""
                    self.state.last_update = time()
                else:
                    # Port is open but the firmware is silent. Do not reopen:
                    # that toggles DTR and can reset the board mid-print.
                    self.state.connected = False
                    self.state.last_error = NO_RESPONSE_ERROR
                    logger.warning("No 'ok' received for a full poll cycle")

            # Sleep in small increments so Ctrl+C is responsive
            for _ in range(int(self.interval / 0.1)):
                if self._stop_event.is_set():
                    return
                sleep(0.1)

    def _poll_once(self) -> bool:
        """Send all status commands and update state.

        Returns True if at least one command was acknowledged with 'ok'.
        """
        responded = False

        # M105 — temperatures
        lines = self.conn.send_command("M105")
        responded |= _got_ok(lines)
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
        responded |= _got_ok(lines)
        for line in lines:
            printing, done, total = parse_m27(line)
            if printing or "Not SD printing" in line:
                self.state.sd_printing = printing
                self.state.sd_bytes_done = done
                self.state.sd_bytes_total = total
                break

        # M114 — position
        lines = self.conn.send_command("M114")
        responded |= _got_ok(lines)
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
        responded |= _got_ok(lines)
        for line in lines:
            fr = parse_m220(line)
            if fr is not None:
                self.state.feedrate_percent = fr
                break

        return responded
