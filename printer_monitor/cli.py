"""CLI entry point: argparse, threading, signal handling."""

import argparse
import logging
import signal
import sys
from time import sleep

from rich.live import Live

from .dashboard import build_dashboard
from .serial_conn import PrinterPoller, SerialConnection
from .state import PrinterState


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="wanhao-d12-230-cli-monitor",
        description="Live terminal dashboard for Wanhao D12 230",
    )
    parser.add_argument(
        "port",
        nargs="?",
        default="/dev/ttyUSB0",
        help="Serial port (default: /dev/ttyUSB0)",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="Baud rate (default: 115200)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.5,
        help="Polling interval in seconds (default: 2.5)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging to printer_monitor.log",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if args.verbose:
        logging.basicConfig(
            filename="printer_monitor.log",
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

    state = PrinterState()
    conn = SerialConnection(port=args.port, baudrate=args.baud)
    poller = PrinterPoller(conn=conn, state=state, interval=args.interval)

    # Graceful shutdown on Ctrl+C
    def handle_signal(signum: int, frame: object) -> None:
        poller.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    poller.start()

    try:
        with Live(build_dashboard(state), refresh_per_second=2) as live:
            while poller.is_alive():
                live.update(build_dashboard(state))
                sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        poller.stop()
        poller.join(timeout=3.0)

    if state.last_error:
        print(f"\nExited due to error: {state.last_error}", file=sys.stderr)
        sys.exit(1)
