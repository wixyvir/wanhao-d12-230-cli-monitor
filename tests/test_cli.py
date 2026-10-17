"""Tests for CLI argument parsing."""

import pytest

from printer_monitor.cli import parse_args


class TestParseArgs:
    def test_dashboard_defaults(self):
        args = parse_args([])
        assert args.command is None
        assert args.port == "/dev/ttyUSB0"
        assert args.baud == 115200
        assert args.interval == 2.5
        assert args.verbose is False

    def test_dashboard_port(self):
        args = parse_args(["--port", "/dev/ttyUSB1"])
        assert args.command is None
        assert args.port == "/dev/ttyUSB1"

    def test_serve_defaults(self):
        args = parse_args(["serve"])
        assert args.command == "serve"
        assert args.port == "/dev/ttyUSB0"
        assert args.baud == 115200
        assert args.interval == 2.5
        assert args.verbose is False
        assert args.host == "0.0.0.0"
        assert args.http_port == 8000

    def test_serve_port_after_subcommand(self):
        args = parse_args(
            ["serve", "--http-port", "8111", "--port", "/dev/serial/by-id/usb-x"]
        )
        assert args.port == "/dev/serial/by-id/usb-x"
        assert args.http_port == 8111

    def test_common_options_before_subcommand_are_kept(self):
        args = parse_args(["--port", "/dev/ttyUSB1", "-v", "--baud", "250000", "serve"])
        assert args.command == "serve"
        assert args.port == "/dev/ttyUSB1"
        assert args.verbose is True
        assert args.baud == 250000

    def test_positional_port_rejected(self):
        with pytest.raises(SystemExit):
            parse_args(["serve", "/dev/ttyUSB1"])
