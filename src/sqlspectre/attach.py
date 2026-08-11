## Wire an ASGI app to one or more SQLAlchemy engines.

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from sqlspectre.config import get_settings
from sqlspectre.engine import instrument_engine
from sqlspectre.middleware import Middleware
from sqlspectre.recorder import Recorder


class SpectreHandle:
    def __init__(self, recorder: Recorder | None) -> None:
        self.recorder = recorder
        self.engines: dict[str, Any] = {}

    def instrument(self, engine: Any, engine_id: str | None = None) -> str | None:
        if self.recorder is None:
            return None
        eid = instrument_engine(engine, self.recorder, engine_id=engine_id)
        self.engines[eid] = engine
        return eid

    def get_recorder(self) -> Recorder | None:
        return self.recorder

    def start(self) -> dict[str, Any] | None:
        """Start (or resume) recording. Raises RuntimeError if already running."""
        if self.recorder is None:
            return None
        logging.info("Starting sqlspectre recording")
        return self.recorder.start()

    def pause(self) -> dict[str, Any] | None:
        if self.recorder is None:
            return None
        return self.recorder.pause()

    def stop(self) -> dict[str, Any] | None:
        """Finalize the current recording and return its details."""
        if self.recorder is None:
            return None
        return self.recorder.stop()

    def details(self) -> dict[str, Any] | None:
        if self.recorder is None:
            return None
        return self.recorder.details()

    def close(self) -> None:
        if self.recorder is not None:
            self.recorder.close()


def _as_pairs(value: Any) -> list[tuple[str | None, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [(str(k), v) for k, v in value.items()]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [(None, v) for v in value]
    return [(None, value)]


def attach(
    app: Any,
    engine: Any = None,
    *,
    engines: Any = None,
    output: str | None = None,
    enabled: bool | None = None,
) -> SpectreHandle:
    s = get_settings()
    out = s.output if output is None else output
    on = s.enabled if enabled is None else enabled

    if not on:
        return SpectreHandle(None)

    pairs = _as_pairs(engines) + _as_pairs(engine)
    if not pairs:
        raise TypeError("attach() requires at least one engine via engine= or engines=")

    recorder = Recorder(
        output=out,
        flush_interval=s.flush_interval,
        max_buffer=s.max_buffer,
        output_format=s.output_format,
    )

    handle = SpectreHandle(recorder)
    for explicit_id, eng in pairs:
        handle.instrument(eng, engine_id=explicit_id)
    app.add_middleware(Middleware, recorder=recorder)
    return handle


def get_recorder(app: Any) -> Recorder | None:
    for middleware in app.user_middleware:
        if isinstance(middleware, Middleware):
            return middleware.recorder
    return None
