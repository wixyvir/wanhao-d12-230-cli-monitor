"""Shared printer state dataclass."""

from dataclasses import dataclass, field
from time import time


@dataclass
class HeaterState:
    current: float = 0.0
    target: float = 0.0
    power: int = 0  # 0-127 raw PWM from firmware


@dataclass
class PrinterState:
    # Temperatures (from M105)
    hotend0: HeaterState = field(default_factory=HeaterState)
    hotend1: HeaterState = field(default_factory=HeaterState)
    bed: HeaterState = field(default_factory=HeaterState)

    # SD print progress (from M27)
    sd_printing: bool = False
    sd_bytes_done: int = 0
    sd_bytes_total: int = 0

    # Position (from M114)
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    e: float = 0.0

    # Feedrate (from M220)
    feedrate_percent: int = 100

    # Connection metadata
    connected: bool = False
    last_update: float = field(default_factory=time)
    last_error: str = ""

    @property
    def sd_progress(self) -> float:
        if self.sd_bytes_total <= 0:
            return 0.0
        return (self.sd_bytes_done / self.sd_bytes_total) * 100.0
