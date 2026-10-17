"""Tests for serial port resolution and poller robustness (no printer needed)."""

import termios
from time import monotonic, sleep
from unittest.mock import MagicMock

import pytest

from printer_monitor import serial_conn
from printer_monitor.serial_conn import (
    NO_RESPONSE_ERROR,
    PrinterPoller,
    SerialConnection,
    find_by_id_link,
    resolve_port,
)
from printer_monitor.state import PrinterState


def wait_for(predicate, timeout: float = 3.0) -> bool:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if predicate():
            return True
        sleep(0.01)
    return predicate()


@pytest.fixture
def dev(tmp_path):
    """Fake /dev with ttyUSB0 and a by-id link pointing to it."""
    (tmp_path / "by-id").mkdir()
    (tmp_path / "ttyUSB0").touch()
    (tmp_path / "by-id" / "usb-1a86_USB_Serial-if00-port0").symlink_to(
        tmp_path / "ttyUSB0"
    )
    return tmp_path


def reenumerate(dev, new_name: str = "ttyUSB1") -> None:
    """Simulate a USB unplug/replug that gives the device a new name."""
    link = dev / "by-id" / "usb-1a86_USB_Serial-if00-port0"
    (dev / "ttyUSB0").unlink()
    link.unlink()
    (dev / new_name).touch()
    link.symlink_to(dev / new_name)


class TestFindByIdLink:
    def test_matching_device(self, dev):
        link = find_by_id_link(str(dev / "ttyUSB0"), str(dev / "by-id"))
        assert link == str(dev / "by-id" / "usb-1a86_USB_Serial-if00-port0")

    def test_link_itself(self, dev):
        link = str(dev / "by-id" / "usb-1a86_USB_Serial-if00-port0")
        assert find_by_id_link(link, str(dev / "by-id")) == link

    def test_no_match(self, dev):
        (dev / "ttyUSB5").touch()
        assert find_by_id_link(str(dev / "ttyUSB5"), str(dev / "by-id")) is None

    def test_missing_dir(self, dev):
        assert find_by_id_link(str(dev / "ttyUSB0"), str(dev / "nope")) is None


class TestResolvePort:
    def test_configured_exists(self, dev):
        configured = str(dev / "ttyUSB0")
        assert resolve_port(configured, None, str(dev / "ttyUSB*")) == configured

    def test_remembered_link_after_reenumeration(self, dev):
        link = str(dev / "by-id" / "usb-1a86_USB_Serial-if00-port0")
        reenumerate(dev)
        assert resolve_port(str(dev / "ttyUSB0"), link, str(dev / "ttyUSB*")) == link

    def test_remembered_link_preferred_over_configured(self, dev):
        # Another device took the old name: the by-id link still wins
        link = str(dev / "by-id" / "usb-1a86_USB_Serial-if00-port0")
        reenumerate(dev)
        (dev / "ttyUSB0").touch()
        assert resolve_port(str(dev / "ttyUSB0"), link, str(dev / "ttyUSB*")) == link

    def test_single_fallback(self, dev):
        reenumerate(dev)
        resolved = resolve_port(str(dev / "ttyUSB0"), None, str(dev / "ttyUSB*"))
        assert resolved == str(dev / "ttyUSB1")

    def test_several_fallbacks_does_not_guess(self, dev):
        reenumerate(dev)
        (dev / "ttyUSB2").touch()
        configured = str(dev / "ttyUSB0")
        assert resolve_port(configured, None, str(dev / "ttyUSB*")) == configured

    def test_nothing_found(self, tmp_path):
        configured = str(tmp_path / "ttyUSB0")
        assert resolve_port(configured, None, str(tmp_path / "ttyUSB*")) == configured


class TestSerialConnection:
    def test_open_follows_reenumeration(self, dev, monkeypatch):
        opened = []

        def fake_serial(port, baudrate, timeout):
            opened.append(port)
            return MagicMock()

        monkeypatch.setattr(serial_conn, "BY_ID_DIR", str(dev / "by-id"))
        monkeypatch.setattr(serial_conn, "FALLBACK_GLOB", str(dev / "ttyUSB*"))
        monkeypatch.setattr(serial_conn.serial, "Serial", fake_serial)

        conn = SerialConnection(str(dev / "ttyUSB0"))
        conn.open()
        assert conn.active_port == str(dev / "ttyUSB0")

        reenumerate(dev)
        conn.open()
        link = str(dev / "by-id" / "usb-1a86_USB_Serial-if00-port0")
        assert conn.active_port == link
        assert opened == [str(dev / "ttyUSB0"), link]

    def test_close_swallows_errors(self):
        conn = SerialConnection("/dev/fake")
        conn._serial = MagicMock()
        conn._serial.close.side_effect = termios.error(5, "Input/output error")
        conn.close()
        assert conn._serial is None


class FakeConnection:
    port = "/dev/fake"

    def __init__(self):
        self.open_calls = 0
        self.close_calls = 0
        self.commands = 0
        self.failures: list[Exception] = []
        self.silent = False

    def open(self) -> None:
        self.open_calls += 1

    def close(self) -> None:
        self.close_calls += 1

    def send_command(self, command: str) -> list[str]:
        self.commands += 1
        if self.failures:
            raise self.failures.pop(0)
        if self.silent:
            return []
        return ["ok"]


@pytest.fixture
def poller_factory():
    pollers = []

    def make(conn):
        state = PrinterState()
        poller = PrinterPoller(conn=conn, state=state, interval=0.1)
        pollers.append(poller)
        return poller, state

    yield make

    for poller in pollers:
        poller.stop()
        poller.join(timeout=3.0)


class TestPrinterPoller:
    def test_survives_termios_error(self, poller_factory):
        # termios.error is not an OSError: it used to kill the poller thread
        conn = FakeConnection()
        conn.failures.append(termios.error(5, "Input/output error"))
        poller, state = poller_factory(conn)
        poller.start()

        assert wait_for(lambda: conn.open_calls >= 2 and state.connected)
        assert poller.is_alive()
        assert conn.close_calls >= 1
        assert wait_for(lambda: state.last_error == "")

    def test_silent_printer_marks_disconnected_without_reopening(self, poller_factory):
        conn = FakeConnection()
        conn.silent = True
        poller, state = poller_factory(conn)
        poller.start()

        assert wait_for(lambda: state.last_error == NO_RESPONSE_ERROR)
        assert state.connected is False
        stale_update = state.last_update

        seen = conn.commands
        assert wait_for(lambda: conn.commands >= seen + 8)
        assert state.last_update == stale_update
        assert conn.open_calls == 1
        assert conn.close_calls == 0

        conn.silent = False
        assert wait_for(lambda: state.connected and state.last_error == "")
        assert state.last_update > stale_update

    def test_disconnected_after_stop(self, poller_factory):
        conn = FakeConnection()
        poller, state = poller_factory(conn)
        poller.start()

        assert wait_for(lambda: state.connected)
        poller.stop()
        poller.join(timeout=3.0)
        assert not poller.is_alive()
        assert state.connected is False
        assert conn.close_calls >= 1
