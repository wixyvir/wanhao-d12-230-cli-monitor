"""Rich Live terminal dashboard for printer status."""

from time import time

from rich.console import Group
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from .state import HeaterState, PrinterState

TEMP_TOLERANCE = 2.0  # degrees — within this range counts as "at target"


def _temp_style(heater: HeaterState) -> str:
    """Return color based on how close current is to target."""
    if heater.target == 0.0:
        return "dim"
    diff = abs(heater.current - heater.target)
    if diff <= TEMP_TOLERANCE:
        return "green"
    return "yellow"


def _format_target(target: float) -> str:
    if target == 0.0:
        return "off"
    return f"{target:.1f}°C"


def _heater_power_pct(heater: HeaterState) -> str:
    """Convert raw PWM 0-127 to percentage."""
    pct = round(heater.power / 127 * 100)
    return f"{pct}%"


def build_dashboard(state: PrinterState) -> Panel:
    """Build the full dashboard panel from current printer state."""
    sections: list[object] = []

    # --- Temperatures ---
    temp_table = Table(
        show_header=True,
        header_style="bold",
        box=None,
        padding=(0, 2),
    )
    temp_table.add_column("Heater", style="bold")
    temp_table.add_column("Current", justify="right")
    temp_table.add_column("Target", justify="right")
    temp_table.add_column("Power", justify="right")

    for label, heater in [
        ("Hotend 0", state.hotend0),
        ("Hotend 1", state.hotend1),
        ("Bed", state.bed),
    ]:
        style = _temp_style(heater)
        temp_table.add_row(
            label,
            Text(f"{heater.current:.1f}°C", style=style),
            Text(_format_target(heater.target), style=style),
            Text(_heater_power_pct(heater), style=style),
        )

    sections.append(Text("TEMPERATURES", style="bold underline"))
    sections.append(temp_table)
    sections.append(Text(""))

    # --- Print Progress ---
    sections.append(Text("PRINT PROGRESS", style="bold underline"))

    if state.sd_printing:
        status_text = Text("Status: SD Printing", style="green")
    else:
        status_text = Text("Status: Idle", style="dim")
    sections.append(status_text)

    progress = state.sd_progress
    bar = ProgressBar(total=100, completed=progress, width=40)
    progress_line = Text()
    progress_line.append_text(Text(f"  {progress:5.1f}%"))
    sections.append(bar)
    sections.append(progress_line)
    sections.append(Text(""))

    # --- Position & Motion ---
    sections.append(Text("POSITION & MOTION", style="bold underline"))
    pos_text = Text(
        f"X: {state.x:.2f}  Y: {state.y:.2f}  Z: {state.z:.2f}  E: {state.e:.2f}"
    )
    sections.append(pos_text)
    sections.append(Text(f"Feedrate: {state.feedrate_percent}%"))
    sections.append(Text(""))

    # --- Status Bar ---
    elapsed = time() - state.last_update
    if state.connected:
        conn_text = Text("Connected", style="green")
    elif state.last_error:
        conn_text = Text(f"Error: {state.last_error}", style="red")
    else:
        conn_text = Text("Disconnected", style="red")

    update_text = Text(f"Updated {elapsed:.0f}s ago", style="dim")
    status_line = Text()
    status_line.append_text(conn_text)
    status_line.append("  |  ")
    status_line.append_text(update_text)
    sections.append(status_line)

    return Panel(
        Group(*sections),
        title="[bold]Wanhao D12 230 Monitor[/bold]",
        border_style="blue",
        width=60,
    )
