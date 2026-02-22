# Contributing to wanhao-d12-230-cli-monitor

Thanks for your interest in contributing! :factory:

## Development Setup

```bash
git clone https://github.com/wixyvir/wanhao-d12-230-cli-monitor.git
cd wanhao-d12-230-cli-monitor
poetry install
```

## Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
# Check for lint errors
poetry run ruff check .

# Auto-fix lint errors
poetry run ruff check --fix .

# Check formatting
poetry run ruff format --check .

# Auto-format
poetry run ruff format .
```

Configuration is in `pyproject.toml`: target Python 3.10, line length 88, rules E/F/I/W.

## Testing

```bash
poetry run pytest -v
```

Tests are in `tests/` and cover the G-code response parsers. No physical printer is needed to run them.

## Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b my-feature`)
3. Make your changes
4. Ensure `ruff check .` and `ruff format --check .` pass
5. Ensure `pytest -v` passes
6. Commit with a clear message describing **why**, not just **what**
7. Open a pull request against `main`

## Reporting Bugs

Please [open an issue](https://github.com/wixyvir/wanhao-d12-230-cli-monitor/issues) with:
- Your Python version (`python --version`)
- Your OS and kernel version (`uname -a`)
- The serial device path you're using
- Relevant output or error messages
- If possible, attach a `printer_monitor.log` from a verbose run (`-v` flag)

## Printer Compatibility Reports

If you've tested this tool with a printer other than the Wanhao D12 230, we'd love to hear about it! Open an issue with:
- Printer make and model
- Firmware name and version
- What worked and what didn't
