"""FastAPI REST server exposing printer status."""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from .serial_conn import PrinterPoller, SerialConnection
from .state import PrinterState


class HeaterResponse(BaseModel):
    current: float
    target: float
    power: int


class StatusResponse(BaseModel):
    connected: bool
    last_update: float
    last_error: str

    hotend0: HeaterResponse
    hotend1: HeaterResponse
    bed: HeaterResponse

    sd_printing: bool
    sd_bytes_done: int
    sd_bytes_total: int
    sd_progress: float

    x: float
    y: float
    z: float
    e: float

    feedrate_percent: int


def _state_to_response(state: PrinterState) -> dict[str, Any]:
    return {
        "connected": state.connected,
        "last_update": state.last_update,
        "last_error": state.last_error,
        "hotend0": {
            "current": state.hotend0.current,
            "target": state.hotend0.target,
            "power": state.hotend0.power,
        },
        "hotend1": {
            "current": state.hotend1.current,
            "target": state.hotend1.target,
            "power": state.hotend1.power,
        },
        "bed": {
            "current": state.bed.current,
            "target": state.bed.target,
            "power": state.bed.power,
        },
        "sd_printing": state.sd_printing,
        "sd_bytes_done": state.sd_bytes_done,
        "sd_bytes_total": state.sd_bytes_total,
        "sd_progress": state.sd_progress,
        "x": state.x,
        "y": state.y,
        "z": state.z,
        "e": state.e,
        "feedrate_percent": state.feedrate_percent,
    }


def create_app(
    port: str = "/dev/ttyUSB0",
    baudrate: int = 115200,
    interval: float = 2.5,
) -> FastAPI:
    state = PrinterState()
    conn = SerialConnection(port=port, baudrate=baudrate)
    poller = PrinterPoller(conn=conn, state=state, interval=interval)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        poller.start()
        yield
        poller.stop()
        poller.join(timeout=3.0)

    app = FastAPI(
        title="Wanhao D12 230 Printer Monitor",
        description="REST API for monitoring Wanhao D12 230 3D printer status",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/status", response_model=StatusResponse)
    def get_status() -> dict[str, Any]:
        return _state_to_response(state)

    return app
