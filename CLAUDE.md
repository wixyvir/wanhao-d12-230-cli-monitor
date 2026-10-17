# :factory: wanhao-d12-230-cli-monitor — CLAUDE.md

## Project Overview

Terminal dashboard for Wanhao D12 230 3D printer, using pyserial + Rich.

**Important:** The pip/CLI name is `wanhao-d12-230-cli-monitor` but the Python import path is `printer_monitor`.

## Commands

```bash
poetry install                              # Install dependencies
poetry run pytest -v                        # Run unit tests (no printer needed)
poetry run wanhao-d12-230-cli-monitor       # Launch the dashboard (requires printer)
poetry run wanhao-d12-230-cli-monitor --help  # Show CLI options
poetry run ruff check .                     # Lint
poetry run ruff check --fix .               # Lint with auto-fix
poetry run ruff format .                    # Format code
poetry run ruff format --check .            # Check formatting
poetry build                                # Build wheel + sdist
```

## Architecture

- `printer_monitor/state.py` — `PrinterState` + `HeaterState` dataclasses (shared between threads)
- `printer_monitor/parsers.py` — Pure functions parsing M105/M27/M114/M220 G-code responses
- `printer_monitor/serial_conn.py` — `SerialConnection` (send/receive) + `PrinterPoller` (daemon thread)
- `printer_monitor/dashboard.py` — `build_dashboard()` returns a Rich Panel from `PrinterState`
- `printer_monitor/cli.py` — Argparse entry point with `serve` subcommand, wires poller thread + Rich Live loop
- `printer_monitor/server.py` — FastAPI REST API (`create_app` factory, `/status` endpoint, Pydantic response models)
- `tests/test_parsers.py` — Unit tests for all parsers (no printer needed)
- `tests/test_serial_conn.py` — Port resolution + poller robustness tests (fake connection, `tmp_path` device files)
- `tests/test_cli.py` — Argparse tests for dashboard and `serve` options

## Key Conventions

- Parsers are pure functions with no side effects — easy to test
- The poller thread is a daemon and uses `threading.Event` for clean shutdown
- Temperature power is raw PWM 0-127 from Marlin, converted to percentage in the dashboard
- `echo:busy: processing` lines extend command timeout rather than being treated as errors
- The poller must never die: its loops catch `Exception` (e.g. `termios.error` from a vanished USB device is *not* an `OSError`), `SerialConnection.close()` never raises, and `run()` always leaves `state.connected = False` on exit
- Port resolution on (re)open (`resolve_port`): remembered `/dev/serial/by-id` link → configured `--port` → the only `/dev/ttyUSB*` (never guesses among several)
- A poll cycle with no `ok` at all marks the state disconnected (`"No response from printer"`) but does **not** reopen the port: reopening toggles DTR, which can reset the board mid-print
- The serial port is the `--port` option (no positional). Shared options are added to both parsers; the `serve` copy uses `argparse.SUPPRESS` defaults so options given before the subcommand are not overwritten

## CI

GitHub Actions runs on push to `main` and PRs: Python 3.10–3.13 matrix with `ruff check`, `ruff format --check`, and `pytest -v`.
