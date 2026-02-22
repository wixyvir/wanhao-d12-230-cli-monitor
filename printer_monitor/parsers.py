"""G-code response parsers for Marlin firmware."""

import re

from .state import HeaterState


def parse_m105(line: str) -> dict[str, HeaterState]:
    """Parse M105 temperature response.

    Handles both standalone and 'ok'-prefixed lines:
      ok T:204.77 /205.00 B:50.71 /50.00 T0:204.77 /205.00 T1:23.50 /0.00 @:95 B@:0
      T:204.77 /205.00 B:50.71 /50.00 T0:204.77 /205.00 T1:23.50 /0.00 @:95 B@:0

    Returns dict with keys: 'hotend0', 'hotend1', 'bed'.
    """
    result: dict[str, HeaterState] = {}

    # Extract heater power values: @:N is hotend0 power, B@:N is bed power
    power_hotend0 = 0
    power_bed = 0

    m = re.search(r"(?<![BT])@:(\d+)", line)
    if m:
        power_hotend0 = int(m.group(1))

    m = re.search(r"B@:(\d+)", line)
    if m:
        power_bed = int(m.group(1))

    # T0:current /target
    m = re.search(r"T0:([\d.]+)\s*/\s*([\d.]+)", line)
    if m:
        result["hotend0"] = HeaterState(
            current=float(m.group(1)),
            target=float(m.group(2)),
            power=power_hotend0,
        )

    # T1:current /target
    m = re.search(r"T1:([\d.]+)\s*/\s*([\d.]+)", line)
    if m:
        result["hotend1"] = HeaterState(
            current=float(m.group(1)),
            target=float(m.group(2)),
            power=0,
        )

    # B:current /target
    m = re.search(r"B:([\d.]+)\s*/\s*([\d.]+)", line)
    if m:
        result["bed"] = HeaterState(
            current=float(m.group(1)),
            target=float(m.group(2)),
            power=power_bed,
        )

    # Fallback: if no T0 found but bare T: exists, use it as hotend0
    if "hotend0" not in result:
        m = re.search(r"(?<![T\d])T:([\d.]+)\s*/\s*([\d.]+)", line)
        if m:
            result["hotend0"] = HeaterState(
                current=float(m.group(1)),
                target=float(m.group(2)),
                power=power_hotend0,
            )

    return result


def parse_m27(line: str) -> tuple[bool, int, int]:
    """Parse M27 SD print progress response.

    Returns (is_printing, bytes_done, bytes_total).
    """
    m = re.search(r"SD printing byte (\d+)/(\d+)", line)
    if m:
        return True, int(m.group(1)), int(m.group(2))

    if "Not SD printing" in line:
        return False, 0, 0

    # Unknown format — return not printing
    return False, 0, 0


def parse_m114(line: str) -> dict[str, float]:
    """Parse M114 position response.

    Example: X:100.00 Y:50.00 Z:10.50 E:1234.56
    Returns dict with keys: 'x', 'y', 'z', 'e'.
    """
    result: dict[str, float] = {}
    for axis in ("X", "Y", "Z", "E"):
        m = re.search(rf"{axis}:([\d.-]+)", line)
        if m:
            result[axis.lower()] = float(m.group(1))
    return result


def parse_m220(line: str) -> int | None:
    """Parse M220 feedrate response.

    Example: FR:100%
    Returns feedrate percentage or None if not parseable.
    """
    m = re.search(r"FR:(\d+)%", line)
    if m:
        return int(m.group(1))
    return None
