# wanhao-d12-230-cli-monitor

A lightweight, terminal-based live dashboard for the **Wanhao D12 230** 3D printer over USB serial.

If you just want to keep an eye on temperatures, print progress, and position without running a full OctoPrint server, this tool gives you a clean Rich-powered terminal UI that refreshes in real time.

## Features

- **Dual hotend + heated bed temperatures** with current/target/power display
- **SD card print progress** with a progress bar
- **Position tracking** (X/Y/Z/E) and feedrate percentage
- **Color-coded status** — green when at target, yellow when heating, dim when off
- **Verbose logging** mode for debugging serial communication
- **Graceful shutdown** on Ctrl+C or SIGTERM

## Requirements

- **Python 3.10+**
- **Linux** (tested on Ubuntu/Debian — uses `/dev/ttyUSB*` serial devices)
- **Wanhao D12 230** connected via USB cable

## Installation

```bash
git clone https://github.com/wixyvir/wanhao-d12-230-cli-monitor.git
cd wanhao-d12-230-cli-monitor
poetry install
```

## Finding Your Serial Device

When the printer is connected via USB, it typically appears as `/dev/ttyUSB0`. To find the correct device:

```bash
# List USB serial devices
ls /dev/ttyUSB*

# Check kernel messages for recently connected devices
dmesg | grep tty
```

If you get a **permission denied** error, add your user to the `dialout` group:

```bash
sudo usermod -aG dialout $USER
# Log out and back in for the change to take effect
```

## Quick Start

```bash
# Default: connect to /dev/ttyUSB0 at 115200 baud
poetry run wanhao-d12-230-cli-monitor

# Specify a different serial port
poetry run wanhao-d12-230-cli-monitor /dev/ttyUSB1

# Custom baud rate and polling interval
poetry run wanhao-d12-230-cli-monitor --baud 250000 --interval 5.0

# Enable verbose logging (writes to printer_monitor.log)
poetry run wanhao-d12-230-cli-monitor -v
```

## CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `port` | `/dev/ttyUSB0` | Serial port to connect to |
| `--baud` | `115200` | Baud rate for serial communication |
| `--interval` | `2.5` | Polling interval in seconds |
| `-v`, `--verbose` | off | Log all serial TX/RX to `printer_monitor.log` |

## Architecture

```
printer_monitor/
├── state.py         # PrinterState + HeaterState dataclasses (shared between threads)
├── parsers.py       # Pure functions parsing M105/M27/M114/M220 G-code responses
├── serial_conn.py   # SerialConnection + PrinterPoller daemon thread
├── dashboard.py     # build_dashboard() → Rich Panel from PrinterState
├── cli.py           # Argparse entry point, signal handling, threading
└── __main__.py      # python -m printer_monitor support
```

The poller thread sends G-code status queries (M105, M27, M114, M220) at the configured interval and updates a shared `PrinterState` dataclass. The main thread runs a Rich `Live` display that renders the dashboard at 2 Hz.

## Compatibility

This tool was built for the **Wanhao D12 230** (dual-extruder, Marlin firmware). It may work with other Marlin-based printers that respond to the same G-code commands (M105, M27, M114, M220), but this has not been tested.

## Known Limitations

- **SD card printing only** — print progress tracking relies on M27 (SD byte progress). Prints sent via USB host (e.g., from a slicer) are not tracked.
- **Linux only** — serial device paths assume `/dev/ttyUSB*`. May work on macOS with `/dev/tty.usbserial-*` but untested.
- **Read-only** — this is a monitoring tool only. It does not send print commands or modify printer settings.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, and how to submit changes.

## License

This project is licensed under the [GNU General Public License v3.0 or later](LICENSE).
