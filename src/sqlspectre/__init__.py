"""sqlspectre — attach → record (v0)."""

from __future__ import annotations

from typing import Any

from sqlspectre.instrument import Middleware, instrument_engine
from sqlspectre.recorder import Recorder

__all__ = [
    "Middleware",
    "Recorder",
    "attach",
    "instrument_engine",
]


class SpectreHandle:
    def __init__(self, recorder: Recorder | None) -> None:
        self.recorder = recorder

    def close(self) -> None:
        if self.recorder is not None:
            self.recorder.close()


def attach(
    app: Any,
    engine: Any,
    output: str = "./spectate",
    enabled: bool = True,
) -> SpectreHandle:
    if not enabled:
        return SpectreHandle(None)

    recorder = Recorder(output=output, flush_interval=10.0)
    instrument_engine(engine, recorder)
    app.add_middleware(Middleware, recorder=recorder)
    
    return SpectreHandle(recorder)
